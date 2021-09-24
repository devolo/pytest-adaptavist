"""Process reporting of tests or test steps."""

import inspect
import re
import signal
from datetime import datetime
from enum import IntEnum
from types import TracebackType
from typing import Any, Optional

import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.python import Function

from ._helpers import get_item_nodeid, get_spec, html_row
from ._pytest_adaptavist import PytestAdaptavist

COLORMAP = {
    "passed": {
        "green": True, "bold": True
    },
    "failed": {
        "red": True, "bold": True
    },
    "blocked": {
        "blue": True, "bold": True
    },
    "skipped": {
        "yellow": True, "bold": True
    }
}


class MetaBlockAborted(Exception):
    """Internal exception used to abort meta block execution."""


class MetaBlock:
    """Context Manager class used for processing/reporting single test blocks/steps."""

    class Action(IntEnum):
        """if condition fails, collect assumption, set block/test to 'Fail' and continue (just like 'assume')"""
        NONE = 0
        FAIL_CONTEXT = 0
        """if condition fails, skip execution of this block/test, set it to 'Fail' and continue with next test (just like 'assert')"""
        FAIL_METHOD = 1
        """if condition fails, skip execution of this block, set it to 'Blocked' and continue with next block"""
        STOP_CONTEXT = 2
        """if condition fails, skip execution of this block/test, set it to 'Blocked' and continue with next test"""
        STOP_METHOD = 3
        """if condition fails, skip execution of this block/test, set it to 'Blocked' and block following tests as well"""
        STOP_SESSION = 4
        """if condition fails, skip execution of this block/test, set it to 'Fail' and block following tests"""
        FAIL_SESSION = 5
        """if condition fails, skip execution of this block/test, set it to 'Blocked' and exit session"""
        EXIT_SESSION = -1

    def __init__(self, request: FixtureRequest, timeout: int, step: Optional[int] = None):
        self.item = request.node
        self.item_name = self.item.name + ("_" + str(step) if step else "")
        self.step = step
        self.start = datetime.now().timestamp()
        self.stop = datetime.now().timestamp()
        self.timeout = timeout
        self.adaptavist: PytestAdaptavist = request.config.pluginmanager.getplugin("_adaptavist")
        self.data = self.adaptavist.test_result_data.setdefault(self.item.fullname + ("_" + str(step) if step else ""), {"comment": None, "attachment": None})
        self.failed_assumptions = getattr(pytest, "_failed_assumptions", [])[:]

    @staticmethod
    def _timeout_handler(signum, frame):
        raise TimeoutError("The test step exceeded its timewindow and timed out")

    def __enter__(self):
        if self.step:
            # gibt's pretty --> pretty prüfen ob pretty an ist.
            # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)')
            build_terminal_report(when="setup", item=self.item, step=self.step, level=2)
        self.start = datetime.now().timestamp()
        self.adaptavist.failed_assumptions_step = []
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout)
        return self

    def __exit__(self, exc_type: type, exc_value: Exception, traceback: TracebackType):
        signal.alarm(0)
        self.stop = datetime.now().timestamp()
        if exc_type is TimeoutError:
            self.data["blocked"] = True
            pytest.skip(msg=f"Blocked. {self.item_name} failed: The test step exceeded its timewindow and timed out")
        skip_status = self.item.get_closest_marker("block") or self.item.get_closest_marker("skip")

        # if method was blocked dynamically (during call) an appropriate marker is used
        # to handle the reporting in the same way as for statically blocked methods
        # (status will be reported as "Blocked" with given comment in Adaptavist)
        if not skip_status and (exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception)  # type:ignore
                                or exc_type in (None, MetaBlockAborted) and self.data.get("blocked") is True):
            reason = self.data.get("comment") or (
                str(exc_value).partition("\n")[0] if exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception) else "")  # type:ignore

            skip_status = pytest.mark.block(reason=reason) if ((exc_type and exc_type is pytest.block.Exception)  # type:ignore
                                                               or self.data.get("blocked", None) is True) else pytest.mark.skip(reason=reason)

        # report exceptions
        if exc_type and exc_type is not MetaBlockAborted:
            exc_info = self.adaptavist.build_exception_info(self.item.fullname, exc_type, exc_value, traceback)

            if (exc_info and exc_info not in (self.data.get("comment") or "") and (exc_type is not pytest.skip.Exception) and not skip_status):
                self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row(False, exc_info)))

        passed = not exc_type and (len(self.adaptavist.failed_assumptions_step) <= len(self.failed_assumptions))
        status = ("passed" if passed else "failed") if not skip_status else ("blocked" if
                                                                             (skip_status.name == "block" or self.data.get("blocked")) else "skipped")

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid") \
            if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist") == "each" \
            else None
        getattr(self.item, "meta_block_cb",
                lambda **kwargs: None)(signature="_".join(filter(None, (prefix, self.item.name, str(self.step) if self.step else "x"))), status=status)

        if self.step:
            build_terminal_report(when="call", item=self.item, status=status, step=self.step,
                                  level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)'))

        # adjust parent's test result status if necessary (needed for makereport call later)
        if self.adaptavist.test_result_data[self.item.fullname].get("blocked") is True and not passed and not skip_status:
            self.adaptavist.test_result_data[self.item.fullname]["blocked"] = None
        elif self.data.get("blocked") is True:
            self.adaptavist.test_result_data[self.item.fullname]["blocked"] = True

        if not getattr(self.item.config.option, "adaptavist", False):
            # adaptavist reporting disabled: no need to proceed here
            return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

        marker = self.item.get_closest_marker("testcase")
        if marker is not None:

            test_case_key = marker.kwargs["test_case_key"]
            test_step_key = marker.kwargs["test_step_key"]

            if test_step_key or not self.step:
                # if it's a test step method, we should not be here
                # if it's the test case context, we can return here as well
                # pytest_runtest_makereport takes care about reporting in both cases
                return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

            specs = get_spec(get_item_nodeid(self.item))
            self.adaptavist.create_report(test_case_key, self.step, self.stop - self.start, skip_status, passed, self.data, specs)

        self.data["done"] = True  # tell pytest_runtest_makereport that this item has been processed already

        return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

    def check(self, condition: bool, message: Optional[str] = None, action_on_fail: Action = Action.NONE, **kwargs: Any):
        """Check given condition.

            :param condition: the condition to be checked
            :param message: the info test in case of failed condition
            :param action_on_fail: action in case of failed condition (default: continue, just like 'assume')
                    Action.FAIL_CONTEXT: if condition fails, collect assumption, set block/test to 'Fail' and continue (just like 'assume')
                    Action.FAIL_METHOD: if condition fails, skip execution of this block/test, set it to 'Fail' and continue with next test (just like 'assert')
                    Action.STOP_CONTEXT: if condition fails, skip execution of this block, set it to 'Blocked' and continue with next block
                    Action.STOP_METHOD: if condition fails, skip execution of this block/test, set it to 'Blocked' and continue with next test
                    Action.STOP_SESSION: if condition fails, skip execution of this block/test, set it to 'Blocked' and block following tests as well
                    Action.EXIT_SESSION: if condition fails, skip execution of this block/test, set it to 'Blocked' and exit session
            :param kwargs: Arbitrary list of keyword arguments
                    attachment: The attachment as filepath name or file-like object.
                    filename: The optional filename.
                    message_on_fail: the info test in case of failed condition (same as message)
                    message_on_pass: the info test in case of passed condition
                    description: optional details about test results (f.e. can be a html table or more)
        """

        attachment = kwargs.pop("attachment", None)
        filename = kwargs.pop("filename", None)
        description = kwargs.pop("description", None)
        message_on_fail = kwargs.pop("message_on_fail", None) or message or ""
        message_on_pass = kwargs.pop("message_on_pass", "")

        if kwargs:
            raise SyntaxWarning(f"Unknown arguments: {kwargs}")

        if attachment:
            self.data["attachment"] = attachment
            self.data["filename"] = filename

        if not condition and message_on_fail:
            self.data["comment"] = "".join((self.data.get("comment", "") or "", html_row(condition, message_on_fail)))
        elif condition and message_on_pass:
            self.data["comment"] = "".join((self.data.get("comment", "") or "", html_row(condition, message_on_pass)))

        if description:
            self.data["description"] = "<br>".join((self.data.get("description", ""), description))

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid") \
            if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist") == "each" \
            else None
        self.__dict__["numchecks"] = self.__dict__.get("numchecks", 0) + 1
        signature = "_".join(filter(None, (prefix, self.item.name, str(self.step) if self.step else "x", str(self.__dict__["numchecks"]))))
        getattr(self.item, "meta_block_condition_cb", lambda **kwargs: None)(signature=signature,
                                                                             condition=condition,
                                                                             reference=message_on_pass if condition else message_on_fail)

        if condition:
            return

        self._process_condition(action_on_fail, condition, message_on_fail)

    def _process_condition(self, action_on_fail: Action, condition: bool, message_on_fail: str):
        if action_on_fail == self.Action.FAIL_METHOD:
            # FAIL_METHOD: skip execution of this block/test, set it to 'Fail' and continue with next test
            assert condition, message_on_fail
        elif action_on_fail == self.Action.STOP_CONTEXT:
            # STOP_CONTEXT: skip execution of this block, set it to 'Blocked' and continue with next block
            self.data["blocked"] = True
            raise MetaBlockAborted()
        elif action_on_fail == self.Action.STOP_METHOD:
            # STOP_METHOD: skip execution of this block/test, set it to 'Blocked' and continue with next test
            self.data["blocked"] = True
            pytest.skip(msg=f"Blocked. {self.item_name} failed: {message_on_fail}")
        elif action_on_fail == self.Action.STOP_SESSION:
            # STOP_SESSION: skip execution of this block/test, set it to 'Blocked' and block following tests as well
            self.data["blocked"] = True
            seen = True
            for item in self.adaptavist.items:
                if not seen:
                    self.adaptavist.test_result_data[item.fullname]["blocked"] = True  # type:ignore
                    self.adaptavist.test_result_data[item.fullname]["comment"] = f"Blocked. {self.item_name} failed: {message_on_fail}"  # type:ignore
                seen = item.name != self.item.name
            pytest.skip(msg=f"Blocked. {self.item_name} failed: {message_on_fail}")
        elif action_on_fail == self.Action.FAIL_SESSION:
            # FAIL_SESSION: skip execution of this block/test, set it to 'Fail' and block following tests
            seen = True
            for item in self.adaptavist.items:
                if not seen:
                    self.adaptavist.test_result_data[item.fullname]["blocked"] = True  # type:ignore
                    self.adaptavist.test_result_data[item.fullname]["comment"] = f"Blocked. {self.item_name} failed: {message_on_fail}"  # type:ignore
                seen = item.name != self.item.name
            assert condition, message_on_fail
        elif action_on_fail == self.Action.EXIT_SESSION:
            # EXIT_SESSION: skip execution of this block/test, set it to 'Blocked' and exit session
            self.data["blocked"] = True
            pytest.exit(msg="Exiting pytest. {self.item_name} failed: {message_on_fail}")
        else:
            # CONTINUE: try to collect failed assumption, set result to 'Fail' and continue
            pytest.assume(expr=condition, msg=message_on_fail)  # type:ignore


def build_terminal_report(when: str, item: Function, status: str = "", step: int = None, level: int = 1):
    """Generate (pretty) terminal output.
        :param when: The call info ("setup", "call").
        :param item: The item to report.
        :param status: The status ("passed", "failed", "skipped", "blocked").
        :param item: The step index to report.
        :param level: The stack trace level (1 = the caller's level, 2 = the caller's caller level, 3 = ...).
    """

    # extract doc string from source
    (frame, _, line, _, _) = inspect.stack()[level][0:5]
    source_list = inspect.getsourcelines(frame)
    source_code = "".join(source_list[0][line - source_list[1]:])
    docs = re.findall(r"^[\s]*\"\"\"(.*?)\"\"\"", source_code, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    doc_string = inspect.cleandoc(docs[0]) if docs else ""
    reporter = item.config.pluginmanager.getplugin("terminalreporter") or None

    if reporter:
        if when == "setup":
            if step and item.config.option.verbose > 1:
                reporter.write_sep("-", "Step " + str(step), bold=True)
                reporter.write(doc_string + ("\n" if doc_string else ""))  # -s is needed!!
        elif when == "call":
            if not step:
                reporter.write_sep("-", bold=True)
                fill = getattr(reporter, "_tw").fullwidth - getattr(reporter, "_width_of_current_line") - 1
                reporter.write_line(status.upper().rjust(fill), **COLORMAP.get(status))
            if step and item.config.option.verbose > 1:
                fill = getattr(reporter, "_tw").fullwidth - getattr(reporter, "_width_of_current_line") - 1
                reporter.write_line(status.upper().rjust(fill), **COLORMAP.get(status))
