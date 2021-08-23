import signal
from datetime import datetime
from enum import IntEnum

import pytest

from ._helpers import assume, build_exception_info, build_terminal_report, create_report, get_item_name_and_spec, get_item_nodeid, get_marker, html_row


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

    def __init__(self, request, timeout, step=None):
        self.item = request.node
        self.item_name = self.item.name + ("_" + str(step) if step else "")
        self.step = step
        self.start = datetime.now().timestamp()
        self.stop = datetime.now().timestamp()
        self.timeout = timeout
        self.data = pytest.test_result_data.setdefault(self.item.fullname + ("_" + str(step) if step else ""), {"comment": None, "attachment": None})
        self.failed_assumptions = getattr(pytest, "_failed_assumptions", [])[:]

    def _timeout_handler(self, signum, frame):
        raise TimeoutError("The test step exceeded its timewindow and timed out")

    def __enter__(self):
        if self.step:
            build_terminal_report(when="setup", item=self.item, step=self.step,
                                  level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)')
        self.start = datetime.now().timestamp()
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        signal.alarm(0)
        self.stop = datetime.now().timestamp()
        if exc_type is TimeoutError:
            self.data["blocked"] = True
            pytest.skip(msg="Blocked. {0} failed: The test step exceeded its timewindow and timed out".format(self.item_name))
        skip_status = get_marker(self.item, "block") or get_marker(self.item, "skip")

        # if method was blocked dynamically (during call) an appropriate marker is used
        # to handle the reporting in the same way as for statically blocked methods
        # (status will be reported as "Blocked" with given comment in Adaptavist)
        if not skip_status and ((exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception)) or
                                (exc_type in (None, MetaBlockAborted) and self.data.get("blocked", None) is True)):
            reason = self.data.get(
                "comment", None) or (str(exc_value).partition("\n")[0] if exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception) else None)
            skip_status = pytest.mark.block(reason=reason) if ((exc_type and exc_type is pytest.block.Exception)
                                                               or self.data.get("blocked", None) is True) else pytest.mark.skip(reason=reason)

        # report exceptions
        if exc_type and exc_type is not MetaBlockAborted:
            exc_info = build_exception_info(self.item.fullname, exc_type, exc_value, traceback)

            if (
                exc_info
                and exc_info not in (self.data.get("comment") or "")
                and (exc_type is not pytest.skip.Exception)
                and not skip_status
            ):
                self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row(False, exc_info)))

        passed = not exc_type and (len(getattr(pytest, "_failed_assumptions", [])) <= len(self.failed_assumptions))
        status = ("passed" if passed else "failed") if not skip_status else ("blocked" if
                                                                             (skip_status.name == "block" or self.data.get("blocked")) else "skipped")

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid") if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist") == "each" else None
        getattr(self.item, "meta_block_cb",
                lambda **kwargs: None)(signature="_".join(filter(None, (prefix, self.item.name, str(self.step) if self.step else "x"))), status=status)

        if self.step:
            build_terminal_report(when="call", item=self.item, status=status, step=self.step,
                                  level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)'))

        # adjust parent's test result status if necessary (needed for makereport call later)
        if pytest.test_result_data[self.item.fullname].get("blocked", None) is True:
            if not passed and not skip_status:
                pytest.test_result_data[self.item.fullname]["blocked"] = None
        elif self.data.get("blocked", None) is True:
            pytest.test_result_data[self.item.fullname]["blocked"] = True

        if not getattr(self.item.config.option, "adaptavist", False):
            # adaptavist reporting disabled: no need to proceed here
            return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

        marker = get_marker(self.item, "testcase")
        if marker is not None:

            test_case_key = marker.kwargs["test_case_key"]
            test_step_key = marker.kwargs["test_step_key"]

            if test_step_key or not self.step:
                # if it's a test step method, we should not be here
                # if it's the test case context, we can return here as well
                # pytest_runtest_makereport takes care about reporting in both cases
                return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

            _, specs = get_item_name_and_spec(get_item_nodeid(self.item))
            create_report(test_case_key, self.step, self.stop - self.start, skip_status, passed, self.data, specs)

        self.data["done"] = True  # tell pytest_runtest_makereport that this item has been processed already

        return exc_type is MetaBlockAborted  # suppress MetaBlockAborted exception

    def check(self, condition, message=None, action_on_fail: Action = Action.NONE, **kwargs):
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

        attachment = kwargs.pop("attachment")
        filename = kwargs.pop("filename")
        description = kwargs.pop("description")
        message_on_fail = kwargs.pop("message_on_fail", message)
        message_on_pass = kwargs.pop("message_on_pass")

        assert not kwargs, "Unknown arguments: %r" % kwargs

        if attachment:
            self.data["attachment"] = attachment
            self.data["filename"] = filename

        if not condition and message_on_fail:
            self.data["comment"] = "".join((self.data.get("comment", ""), html_row(condition, message_on_fail)))
        elif condition and message_on_pass:
            self.data["comment"] = "".join((self.data.get("comment", ""), html_row(condition, message_on_pass)))

        if description:
            self.data["description"] = "<br>".join((self.data.get("description", ""), description))

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid") if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist") == "each" else None
        self.__dict__["numchecks"] = self.__dict__.get("numchecks", 0) + 1
        getattr(self.item, "meta_block_condition_cb", lambda **kwargs: None)(signature="_".join(
            filter(None, (prefix, self.item.name, str(self.step) if self.step else "x", str(self.__dict__["numchecks"])))),
                                                                             condition=condition,
                                                                             reference=message_on_pass if condition else message_on_fail)

        if condition:
            return

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
            pytest.skip(msg="Blocked. {0} failed: {1}".format(self.item_name, message_on_fail))
        elif action_on_fail == self.Action.STOP_SESSION:
            # STOP_SESSION: skip execution of this block/test, set it to 'Blocked' and block following tests as well
            self.data["blocked"] = True
            seen = True
            for item in pytest.items:
                if not seen:
                    pytest.test_result_data[item.fullname]["blocked"] = True
                    pytest.test_result_data[item.fullname]["comment"] = "Blocked. {0} failed: {1}".format(self.item_name, message_on_fail)
                if item.name == self.item.name:
                    seen = False
            pytest.skip(msg="Blocked. {0} failed: {1}".format(self.item_name, message_on_fail))
        elif action_on_fail == self.Action.FAIL_SESSION:
            # FAIL_SESSION: skip execution of this block/test, set it to 'Fail' and block following tests
            seen = True
            for item in pytest.items:
                if not seen:
                    pytest.test_result_data[item.fullname]["blocked"] = True
                    pytest.test_result_data[item.fullname]["comment"] = "Blocked. {0} failed: {1}".format(self.item_name, message_on_fail)
                if item.name == self.item.name:
                    seen = False
            assert condition, message_on_fail
        elif action_on_fail == self.Action.EXIT_SESSION:
            # EXIT_SESSION: skip execution of this block/test, set it to 'Blocked' and exit session
            self.data["blocked"] = True
            pytest.exit(msg="Exiting pytest. {0} failed: {1}".format(self.item_name, message_on_fail))
        else:
            # CONTINUE: try to collect failed assumption, set result to 'Fail' and continue
            assume(expr=condition, msg=message_on_fail, level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of mb.check)
