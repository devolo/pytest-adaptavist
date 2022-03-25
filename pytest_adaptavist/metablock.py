"""Process reporting of tests or test steps."""

from __future__ import annotations

import signal
from datetime import datetime
from enum import IntEnum
from functools import singledispatch
from io import BufferedReader, BytesIO
from types import FrameType, TracebackType
from typing import Any, Literal, NoReturn, Tuple

import pytest

from ._helpers import Attachment, build_terminal_report, get_item_nodeid, get_spec, html_row
from ._pytest_adaptavist import PytestAdaptavist


class MetaBlockAborted(Exception):
    """Internal exception used to abort meta block execution."""


class MetaBlock:
    """
    Context Manager class used for processing/reporting single test blocks/steps.

    :param request:
    :param timeout: Timeout in seconds
    :param step: step number as integer starting at 1
    """

    class Action(IntEnum):
        """Action to take, if a test case fails."""

        NONE = 0
        FAIL_CONTEXT = 0
        """If condition fails, collect assumption, set block/test to 'Fail' and continue (just like 'assume')."""
        STOP_CONTEXT = 1
        """If condition fails, skip execution of this block, set it to 'Blocked' and continue with next block."""
        FAIL_METHOD = 2
        """If condition fails, skip execution of this block/test, set it to 'Fail' and continue with next test (just like 'assert')."""
        STOP_METHOD = 3
        """If condition fails, skip execution of this block/test, set it to 'Blocked' and continue with next test."""
        FAIL_SESSION = 4
        """If condition fails, skip execution of this block/test, set it to 'Fail' and block following tests."""
        STOP_SESSION = 5
        """If condition fails, skip execution of this block/test, set it to 'Blocked' and block following tests as well."""
        FAIL_EXIT_SESSION = 6
        """If condition fails, skip execution of this block/test, set it to 'Blocked' and exit session."""
        STOP_EXIT_SESSION = 7
        """If condition fails, skip execution of this block/test, set it to 'Blocked' and exit session."""

    def __init__(self, request: pytest.FixtureRequest, timeout: int, action_on_timeout: Action, message_on_timeout: str, step: int | None = None):
        fullname = get_item_nodeid(request.node)
        self.item = request.node
        self.items = request.session.items
        self.item_name = self.item.name + ("_" + str(step) if step else "")
        self.step = step
        self.start = datetime.now().timestamp()
        self.stop = datetime.now().timestamp()
        self.timeout = timeout
        self.action_on_timeout = action_on_timeout
        self.message_on_timeout = message_on_timeout
        self.adaptavist: PytestAdaptavist = request.config.pluginmanager.getplugin("_adaptavist")
        self.data: dict[str, Any] = self.adaptavist.test_result_data.setdefault(fullname + ("_" + str(step) if step else ""), {
            "comment": None, "attachment": None
        })

    @staticmethod
    def _timeout_handler(signum: int, frame: FrameType | None) -> NoReturn:
        """Handle test cases running to long."""
        raise TimeoutError("The test step exceeded its timewindow and timed out")

    def __enter__(self) -> MetaBlock:
        if self.step:
            # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)')
            build_terminal_report(when="setup", item=self.item, step=self.step, level=2)
        self.start = datetime.now().timestamp()
        self.adaptavist.failed_assumptions_step = []
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout)
        return self

    def __exit__(self, exc_type: type, exc_value: Exception, traceback: TracebackType) -> bool:
        signal.alarm(0)
        self.stop = datetime.now().timestamp()
        fullname = get_item_nodeid(self.item)
        if exc_type is TimeoutError:
            self._process_failed_condition(self.action_on_timeout, self.message_on_timeout)
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
            exc_info = self.adaptavist.build_exception_info(fullname, exc_type, exc_value, traceback)

            if (exc_info and exc_info not in (self.data.get("comment") or "") and (exc_type is not pytest.skip.Exception) and not skip_status):
                self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row("failed", exc_info)))

        passed = not exc_type and (len(self.adaptavist.failed_assumptions_step) <= len(getattr(pytest, "_failed_assumptions", [])[:]))
        status: Literal["passed", "failed", "skipped", "blocked"] = ("passed" if passed else "failed") if not skip_status \
            else ("blocked" if (skip_status.name == "block" or self.data.get("blocked")) else "skipped")

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
        if self.adaptavist.test_result_data[fullname].get("blocked") is True and not passed and not skip_status:
            self.adaptavist.test_result_data[fullname]["blocked"] = None
        elif self.data.get("blocked") is True:
            self.adaptavist.test_result_data[fullname]["blocked"] = True

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

    def check(self, condition: bool, message: str | None = None, action_on_fail: Action = Action.NONE, **kwargs: Any):
        """
        Check given condition.

        :param condition: The condition to be checked
        :param message: The info test in case of failed condition
        :param action_on_fail: Action in case of failed condition (default: continue, just like 'assume')
        :key attachment: The attachment as filepath name or file-like object
        :key filename: The optional filename
        :key message_on_fail: The info test in case of failed condition (same as message)
        :key message_on_pass: The info test in case of passed condition
        :key description: Optional details about test results (f.e. can be a html table or more)
        """
        attachment = kwargs.pop("attachment", None)
        filename = kwargs.pop("filename", None)
        description = kwargs.pop("description", None)
        message_on_fail = kwargs.pop("message_on_fail", None) or message or ""
        message_on_pass = kwargs.pop("message_on_pass", "")
        if kwargs:
            raise SyntaxWarning(f"Unknown arguments: {kwargs}")

        if attachment and self.adaptavist.enabled:
            if not self.data.get("attachment_test_case"):
                self.data["attachment_test_case"] = []

            if not self.data.get("attachment_test_step"):
                self.data["attachment_test_step"] = []

            content, name = _read_attachment(attachment)
            if self.step:
                self.data["attachment_test_step"].append(Attachment(content, filename=filename or name or "", step=self.step or 0))
            else:
                self.data["attachment_test_case"].append(Attachment(content, filename=filename or name or "", step=self.step or 0))

        if not condition and message_on_fail:
            self.data["comment"] = "".join((self.data.get("comment", "") or "", html_row("failed", message_on_fail)))
        elif condition and message_on_pass:
            self.data["comment"] = "".join((self.data.get("comment", "") or "", html_row("passed", message_on_pass)))

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

        self._process_failed_condition(action_on_fail, message_on_fail)

    def _process_failed_condition(self, action_on_fail: Action, message_on_fail: str):
        """Process failed condition depending on action_on_fail."""
        fullname = get_item_nodeid(self.item)
        if action_on_fail == self.Action.FAIL_METHOD:
            # FAIL_METHOD: skip execution of this block/test, set it to 'Fail' and continue with next test
            assert False, message_on_fail
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
            for item in self.items:
                item.add_marker("block")
                self.adaptavist.test_result_data[fullname]["blocked"] = True
                self.adaptavist.test_result_data[fullname]["comment"] = f"Blocked. {self.item_name} failed: {message_on_fail}"
            pytest.block(msg=message_on_fail)  # type:ignore
        elif action_on_fail == self.Action.FAIL_SESSION:
            # FAIL_SESSION: skip execution of this block/test, set it to 'Fail' and block following tests
            for item in self.items:
                if item.name not in self.item.name:
                    item.add_marker("block")
                    self.adaptavist.test_result_data[fullname]["blocked"] = True
                    self.adaptavist.test_result_data[fullname]["comment"] = f"Blocked. {self.item_name} failed: {message_on_fail}"
            assert False, message_on_fail
        elif action_on_fail == self.Action.STOP_EXIT_SESSION:
            # EXIT_SESSION: skip execution of this block/test, set it to 'Blocked' and exit session
            self.item.add_marker("block")
            pytest.exit(msg=f"Exiting pytest. {self.item_name} failed: {message_on_fail}", returncode=1)
        elif action_on_fail == self.Action.FAIL_EXIT_SESSION:
            # EXIT_SESSION: skip execution of this block/test, set it to 'Blocked' and exit session
            pytest.exit(msg=f"Exiting pytest. {self.item_name} failed: {message_on_fail}")
        else:
            # CONTINUE: try to collect failed assumption, set result to 'Fail' and continue
            pytest.assume(expr=False, msg=message_on_fail)  # type:ignore


@singledispatch
def _read_attachment(attachment: Any) -> Tuple[BytesIO, str]:
    """Read content of an attachment."""
    raise TypeError(f"Type {type(attachment)} is not supported for attachments.")


@_read_attachment.register
def _(attachment: str) -> Tuple[BytesIO, str]:
    """Read content of an attachment given with filename."""
    with open(attachment, "rb") as file_pointer:
        return BytesIO(file_pointer.read()), file_pointer.name


@_read_attachment.register  # type: ignore
def _(attachment: BufferedReader) -> Tuple[BytesIO, str]:
    """Read content of an attachment given as file pointer."""
    return BytesIO(attachment.read()), attachment.name
