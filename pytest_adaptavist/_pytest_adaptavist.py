"""Connect pytest with Adaptavist."""

from __future__ import annotations

import getpass
import inspect
import os
import re
import sys
import time
from datetime import datetime
from types import FrameType, TracebackType
from typing import Any

import pytest
from _pytest._io.saferepr import saferepr
from _pytest.config import Config
from _pytest.mark.structures import Mark
from _pytest.outcomes import fail
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.terminal import TerminalReporter
from adaptavist import Adaptavist
from adaptavist.const import PRIORITY_HIGH, STATUS_BLOCKED, STATUS_FAIL, STATUS_NOT_EXECUTED, STATUS_PASS
from pytest_assume.plugin import Assumption, FailedAssumption

from ._atm_configuration import ATMConfiguration
from ._helpers import apply_test_case_range, calc_test_result_status, get_item_nodeid, get_option_ini, get_spec, html_row, intersection


class PytestAdaptavist:
    """
    Connects pytest with Adaptavist and takes care about the reporting.

    :param config: The pytest config object
    """
    _ATTRIBUTE_PLACEHOLDERS = re.compile(r"(?<=%\()(.*?)(?=\))")
    _ATTRIBUTE_REPLACEMENT = re.compile(r"%\(.*?\)")

    def __init__(self, config: Config):
        self.config = config
        self.item_status_info: dict[str, Any] = {}
        self.test_refresh_info: dict[str, Any] = {}
        self.test_result_data: dict[str, Any] = {}
        self.report: dict[str, Any] = {}
        self.project_key: str | None = None
        self.test_run_keys: list[str] = []
        self.failed_assumptions: list[Assumption] = []
        self.failed_assumptions_step: list[Assumption] = []
        self.reporter: TerminalReporter = config.pluginmanager.getplugin("terminalreporter")
        self.build_url = ""
        self.code_base = ""
        self.test_plan_key: str | None = None
        self.test_run_key = ""
        self.test_case_order: list[str] = []
        self.test_case_keys: list[str] = []
        self.test_environment: str | None = None
        self.test_case_range: list[str] = []
        self.test_plan_folder = ""
        self.test_run_folder = ""
        self.test_plan_suffix = ""
        self.test_run_suffix = ""
        self.local_user = getpass.getuser().lower()
        self.enabled = get_option_ini(config, "adaptavist")

        self.cfg = ATMConfiguration()
        self.adaptavist: Adaptavist = Adaptavist(self.cfg.get("jira_server", ""), self.cfg.get("jira_username", ""), self.cfg.get("jira_password", ""))

        self.atm_configure()

    def atm_configure(self):
        """Setup adaptavist reporting based on given requirements (config)."""
        if not self.project_key:
            self.project_key = self.cfg.get("project_key", None)

        # support of multiple environments
        # in case of using xdist's "each" mode, a test run for each specified environment is created
        # and test_environment can be used (when given as a list or comma-separated string) to specify keys for each test run resp. worker node
        worker_input = getattr(self.config, "workerinput", {})
        distribution = worker_input.get("options", {}).get("dist", None)
        index = int(worker_input.get("workerid", "gw0").split("gw")[1]) if (distribution == "each") else 0

        entry = self.test_environment or self.cfg.get("test_environment", []) or []
        test_environments = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry
        self.test_environment = test_environments[index if index < len(test_environments) else -1] if test_environments else None

        entry = self.test_case_keys or self.cfg.get("test_case_keys", []) or []
        self.test_case_keys = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        entry = self.test_case_order or self.cfg.get("test_case_order", []) or []
        self.test_case_order = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        entry = self.test_case_range or self.cfg.get("test_case_range", []) or []
        self.test_case_range = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        if not self.test_plan_key:
            self.test_plan_key = self.cfg.get("test_plan_key", None)
        if not self.test_plan_folder:
            self.test_plan_folder = self.cfg.get("test_plan_folder", None)
        if not self.test_plan_suffix:
            self.test_plan_suffix = self.cfg.get("test_plan_suffix", None)
        if not self.test_run_key:
            self.test_run_key = self.cfg.get("test_run_key", None)
        if not self.test_run_folder:
            self.test_run_folder = self.cfg.get("test_run_folder", None)
        if not self.test_run_suffix:
            self.test_run_suffix = self.cfg.get("test_run_suffix", "test run " + datetime.now().strftime("%Y%m%d%H%M"))

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session: pytest.Session, config: Config, items: list[pytest.Item]):  # pylint: disable=unused-argument
        """Collect items matching given requirements and prepare adaptavist reporting."""
        for item in items:
            if (mark := item.get_closest_marker("project")) and not self.project_key:
                self.project_key = mark.kwargs.get("project_key")
            fullname = get_item_nodeid(item)
            # initialize item's status info
            self.item_status_info[fullname] = {}
            # initialize item's test result data (see meta_data function down below)
            self.test_result_data[fullname] = {"comment": None, "attachment": None}

        collected_project_keys: list[str] = []
        collected_items: dict[str, Any] = {}

        self._setup_item_collection(items, collected_project_keys, collected_items)
        self._create_item_collection(items, collected_project_keys, collected_items)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item):
        """This is called before calling the test item. Used to skip test items dynamically (e.g. triggered by some other item or control function)."""
        # Needed to ensure that a class decorator is preferred over a function decorator.
        if (item.cls and getattr(item.cls, "pytestmark", False) and all((mark.name != "block" or "blockif" for mark in item.cls.pytestmark))  # type: ignore
                and not item.get_closest_marker("block") and not item.get_closest_marker("blockif")):
            return

        if skip_status := item.get_closest_marker("blockif"):
            if not skip_status.kwargs.get("reason", ""):
                fail("You need to specify a reason when blocking conditionally.", pytrace=False)
            elif any(skip_status.args):
                pytest.block(msg=skip_status.kwargs["reason"])  # type: ignore

        if skip_status := item.get_closest_marker("block"):
            fullname = get_item_nodeid(item)
            if not (skip_reason := skip_status.kwargs.get("reason", "")) and self.test_result_data[fullname].get("blocked") is True:
                skip_reason = self.test_result_data[fullname].get("comment", "")
            if skip_status.name == "block":
                pytest.block(msg=skip_reason)  # type: ignore

    @pytest.hookimpl()
    def pytest_runtest_logreport(self, report: TestReport):
        """Process the test report produced for each of the setup, call and teardown runtest phases of an item."""
        user_properties: dict[str, Any] = dict(report.user_properties)
        if (user_properties.get("atmcfg") and self.test_run_key and self.test_run_key not in self.test_run_keys):
            self.test_run_keys.append(self.test_run_key)

    @pytest.hookimpl()
    def pytest_assume_fail(self, lineno: int, entry: str):  # pylint: disable=unused-argument
        """Store stack in-case of assumption failure."""
        stack = inspect.stack()
        for index, stack_entry in enumerate(stack):
            if stack_entry.function == "check" and stack_entry.filename.endswith("metablock.py"):
                test_call_index = index + 1
                break
        (frame, _, _, _, contextlist) = stack[test_call_index][:5]
        local_locals = [f"{name:10s} = {saferepr(val)}" for name, val in frame.f_locals.items()]
        self.failed_assumptions_step.append([])
        self.failed_assumptions.append(AdaptavistAssumption((contextlist or [""])[0].lstrip(), frame, local_locals))

    @pytest.hookimpl()
    def pytest_assume_summary_report(self, failed_assumptions: list[Assumption]) -> str:
        """Manipulate the summary that prints at the end."""
        for failed_assumption in zip(failed_assumptions, self.failed_assumptions):
            filename = inspect.getouterframes(failed_assumption[0].tb.tb_frame)[3][1]
            frame = inspect.getouterframes(failed_assumption[0].tb.tb_frame)[2][0]
            msg = frame.f_locals.get("message_on_fail", "")
            context = (msg or failed_assumption[1].entry.strip()) + "\n"
            local_entry = f"{os.path.relpath(filename)}:{failed_assumption[1].line_no}: AssumptionFailure\n\t{context}"
            failed_assumption[0].locals = failed_assumption[1].locals
            failed_assumption[1].entry = local_entry

        report = "\n".join(failed_assumption.longrepr() + "\n\n" for failed_assumption in self.failed_assumptions)\
            if not getattr(pytest, "_showlocals") \
            else "\n".join(failed_assumption.repr() for failed_assumption in self.failed_assumptions)

        self.failed_assumptions = []
        return report

    def create_report(self,
                      test_case_key: str,
                      test_step_key: int | None,
                      execute_time: float,
                      skip_status: Mark | None,
                      passed: bool,
                      test_result_data: dict[str, Any],
                      specs: str = ""):
        """
        Generate adaptavist test results for given item.

        :param test_case_key: Name of the test case in adaptavist test management
        :param test_step_key: Step number starting at 1. Can be empty
        :param execute_time: Executing time as float in seconds
        :param skip_status: pytest marker if test is blocked/skipped
        :param passed: True if test is passed, else False
        :param test_result_data: Dictionary with additional data about the test result like comment or attachment.
        :param specs:
        """
        if not (self.test_run_key or test_case_key in (self.test_case_keys or [])):
            return

        test_result = self.adaptavist.get_test_result(self.test_run_key, test_case_key)

        if not test_result or self.test_refresh_info[test_case_key + specs] != self.test_run_key:
            # create new test result to prevent accumulation of data
            # when using an existing test run key multiple times
            self.adaptavist.create_test_result(test_run_key=self.test_run_key,
                                               test_case_key=test_case_key,
                                               environment=self.test_environment,
                                               executor=self.local_user,
                                               assignee=self.local_user)
            test_result = self.adaptavist.get_test_result(self.test_run_key, test_case_key)
            self.test_refresh_info[test_case_key + specs] = self.test_run_key

        # touch parametrized/repeated items
        for key in self.test_refresh_info:
            if re.search(test_case_key + r"[ \[\b]", key):
                self.test_refresh_info[key] = self.test_run_key

        # get optional meta data (comments, attachments) of test case method
        comment: str = skip_status.kwargs.get("reason", "") if skip_status else test_result_data.get("comment", "")
        description = None if skip_status else test_result_data.get("description")
        attachments_test_case = None if skip_status else test_result_data.get("attachment_test_case")
        attachments_test_steps = None if skip_status else test_result_data.get("attachment_test_step")
        attachment = None if skip_status else test_result_data.get("attachment")

        header = f"---------------------------------------- {datetime.now().strftime('%Y-%m-%d %H:%M')} ----------------------------------------" \
            if specs else ""

        if not skip_status and not test_step_key:
            # update test case with CI related info
            self.adaptavist.edit_test_case(test_case_key,
                                           labels=["automated"],
                                           build_urls=[f"<a href=\"{self.build_url}\">{self.build_url}</a>" if self.build_url else ""],
                                           code_bases=[f"<a href=\"{self.code_base}\">{self.code_base}</a>" if self.code_base else ""])

        if test_step_key:

            # in case of parameterization or repetition the status will be Fail if one iteration failed
            last_result: dict[str, str] = next((result for result in test_result.get("scriptResults", []) if result["index"] == test_step_key - 1), {})

            if skip_status and last_result.get("status") != STATUS_FAIL:
                status = STATUS_BLOCKED if skip_status.name == "block" else STATUS_NOT_EXECUTED
            else:
                status = STATUS_PASS if passed and last_result.get("status") != STATUS_FAIL else STATUS_FAIL

            if status == STATUS_BLOCKED:
                comment = html_row("blocked", comment)

            comments = ((header + "<br>" + "parameterization " + specs + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + (last_result.get("comment", "") if specs else "")

            self.adaptavist.edit_test_script_status(test_run_key=self.test_run_key,
                                                    test_case_key=test_case_key,
                                                    step=test_step_key,
                                                    environment=self.test_environment,
                                                    status=status,
                                                    comment=comments if (specs or last_result.get("status") != STATUS_FAIL) else None,
                                                    executor=self.local_user,
                                                    assignee=self.local_user)

            if attachments_test_steps:
                for ats in attachments_test_steps:
                    self.adaptavist.add_test_script_attachment(test_run_key=self.test_run_key,
                                                               test_case_key=test_case_key,
                                                               step=test_step_key,
                                                               attachment=ats.attachment,
                                                               filename=ats.filename)

            # adjust parent test result status according to current test script results
            test_result = self.adaptavist.get_test_result(self.test_run_key, test_case_key)
            status = calc_test_result_status(test_result.get("scriptResults", []))

            comments = ""
            if skip_status:
                # modify comment to add info about blocked or skipped script steps
                comments = f'Step {test_step_key} {"blocked" if skip_status.name == "block" else "skipped"}'
            elif not passed:
                # modify comment to add info about failure in script steps
                comments = f'Step {test_step_key}{("<br>" + comment + "<br>") if comment else ""} failed:'

            # find the right position to insert comments of this test execution (in case of parametrized or repeated test methods)
            index = test_result.get("comment", "").find("---------------------------------------- ")

            if comment and comments in test_result.get("comment", ""):
                comment = ""
            else:
                comment = (test_result.get("comment", "") + comments) if index < 0 else \
                    (test_result.get("comment", "")[:index] + comments + test_result.get("comment", "")[index:])
            self.adaptavist.edit_test_result_status(test_run_key=self.test_run_key,
                                                    test_case_key=test_case_key,
                                                    environment=self.test_environment,
                                                    status=status,
                                                    comment=comment,
                                                    execute_time=execute_time,
                                                    executor=self.local_user,
                                                    assignee=self.local_user)

        else:
            # change parent test result status only if blocked or failed or if there was no previous failure
            status = test_result.get("status", STATUS_NOT_EXECUTED)
            if status == STATUS_NOT_EXECUTED and skip_status:
                status = STATUS_BLOCKED if skip_status.name == "block" else STATUS_NOT_EXECUTED
            elif status == STATUS_FAIL or (not passed and not skip_status):
                status = STATUS_FAIL
            elif status == STATUS_NOT_EXECUTED:
                status = STATUS_PASS if passed else STATUS_FAIL

            comments = ((header + "<br>" + "parameterization " + specs + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + test_result.get("comment", "")

            self.adaptavist.edit_test_result_status(test_run_key=self.test_run_key,
                                                    test_case_key=test_case_key,
                                                    environment=self.test_environment,
                                                    status=status,
                                                    comment=comments,
                                                    execute_time=execute_time,
                                                    executor=self.local_user,
                                                    assignee=self.local_user)

            if attachments_test_case:
                for atc in attachments_test_case:
                    self.adaptavist.add_test_result_attachment(test_run_key=self.test_run_key,
                                                               test_case_key=test_case_key,
                                                               attachment=atc.attachment,
                                                               filename=atc.filename)

            if attachment:
                self.adaptavist.add_test_result_attachment(test_run_key=self.test_run_key,
                                                           test_case_key=test_case_key,
                                                           attachment=attachment,
                                                           filename=test_result_data["filename"])

    def _build_report_description(self, item: pytest.Item, call: CallInfo, report: TestReport, skip_status: Mark | None):
        """Generate standard test results for given item."""
        fullname = get_item_nodeid(item)
        description = (skip_status.kwargs.get("reason") if skip_status else "") or self.test_result_data[fullname].get("comment") or ""

        if call.when != "teardown" or call.excinfo:
            test_case_key = None
            test_case_name = None
            priority = None
            marker = item.get_closest_marker("testcase")
            if marker is not None:
                test_case_key = marker.kwargs["test_case_key"]
                if test_case_key in (self.test_case_keys or []):
                    test_case_info = self.adaptavist.get_test_case(test_case_key)
                    test_case_name = test_case_info.get("name", None)
                    priority = test_case_info.get("priority", None)

            if (not (call.excinfo and call.excinfo.type is pytest.skip.Exception) and not skip_status and test_case_key):
                subkeys = [key for key in self.test_result_data if key != fullname and key.startswith(fullname)]
                for key in subkeys:
                    description = "<br>".join((description,
                                               f"{key}{' blocked' if self.test_result_data[key].get('blocked', None) is True else ''}:",
                                               self.test_result_data[key].get("comment", None) or ""))

            key = get_item_nodeid(item)

            outcome = report.outcome if not skip_status else ("blocked" if skip_status.name == "block" else "skipped")

            self.report[key] = {
                "test_case_key": test_case_key,
                "test_case_name": test_case_name,
                "priority": priority,
                "status": outcome,
                "duration": report.duration,
                "details": description or "",
                "exc_info": is_unexpected_exception(self.item_status_info[fullname].get("exc_info", (None, None, None))[0])
            }

    def build_exception_info(self, item_name: str, exc_type: type, exc_value: BaseException | Exception, traceback: TracebackType) -> str:
        """
        Generate description info about exceptions.

        :param item_name: Item name in the format of pytest e.g. test_T14:::test_T14
        :param exc_type: Type of the exception. E.g. AssertionError
        :param exc_value: Call value of the exception. E.g. 'assert False' in case of an AssertionError
        :param traceback: The traceback object of the exception
        """
        exc_info = ""
        if exc_type and (exc_type, exc_value, traceback) != self.item_status_info[item_name].get("exc_info", None):
            if exc_type is AssertionError or exc_type is pytest.skip.Exception:
                # in case of assertion only report exception value (not line of code)
                exc_info = str(exc_value).partition("\n")[0]
            else:
                exc_dict = {
                    "path": os.path.relpath(traceback.tb_frame.f_code.co_filename), "line": traceback.tb_lineno, "info": str(exc_value).partition("\n")[0]
                }
                exc_info = f'{exc_dict["info"]} ({exc_dict["path"]}, line {exc_dict["line"]} )'

            # avoid reporting this exception a second time
            self.item_status_info[item_name]["exc_info"] = (exc_type, exc_value, traceback)

        return exc_info

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: CallInfo):
        """This is called at setup, run/call and teardown of test items. Generates adaptavist test run results from test reports."""
        outcome = yield
        report: TestReport = outcome.get_result()

        report.user_properties.append(
            ("atmcfg", {
                "project_key": self.project_key,
                "test_environment": self.test_environment,
                "test_plan_key": self.test_plan_key,
                "test_run_key": self.test_run_key
            }))

        report.user_properties.append(("nodeid", get_item_nodeid(item)))
        report.user_properties.append(("docstr", inspect.cleandoc(item.obj.__doc__ or "")))  # type: ignore

        if call.when not in ("call", "setup") or (item.cls and getattr(item.cls, "pytestmark", False)  # type: ignore
                                                  and all((mark.name != "block" for mark in item.cls.pytestmark))  # type: ignore
                                                  and any((mark.args[0] is True for mark in item.cls.pytestmark if mark.name == "skipif"))):  # type: ignore
            return
        if call.excinfo and call.excinfo.type is pytest.block.Exception:  # type: ignore
            report.blocked = True  # type: ignore

        skip_status = item.get_closest_marker("block") or item.get_closest_marker("skip")
        fullname = get_item_nodeid(item)

        if call.when == "setup":
            if getattr(item.config.option, "adaptavist", False):
                # setup report only if adaptavist reporting is enabled
                self._setup_report(getattr(item.config, "workerinput", {}))
                for user_property in report.user_properties:
                    if user_property[0] == "atmcfg" and isinstance(user_property[1], dict):
                        del user_property[1]["test_environment"]
            if (not call.excinfo and not skip_status and self.test_result_data[fullname].get("blocked", None) is not True):
                # no skipped or blocked methods to report
                return

        # if method was blocked dynamically (during call) an appropriate marker is used
        # to handle the reporting in the same way as for statically blocked methods
        # (status will be reported as "Blocked" with given comment in Adaptavist)
        call_info = call.excinfo and call.excinfo.type in (pytest.block.Exception, pytest.skip.Exception)  # type: ignore
        if not skip_status and (call_info  # type: ignore
                                or not call.excinfo and self.test_result_data[fullname].get("blocked")):
            reason = self.test_result_data[fullname].get("comment") or \
                str(call.excinfo.value).partition("\n")[0] if call_info else ""  # type: ignore
            skip_status = pytest.mark.block(reason=reason) if ((call.excinfo and call.excinfo.type is pytest.block.Exception)  # type: ignore
                                                               or self.test_result_data[fullname].get("blocked")) else pytest.mark.skip(reason=reason)
            if report.outcome != "skipped":
                report.outcome = "skipped"  # to mark this as SKIPPED in pytest reports
                report.longrepr = (__file__,
                                   getattr(sys, "_getframe")().f_lineno if hasattr(sys, "_getframe") else None,
                                   f"Skipped: {reason or 'blocked dynamically or partially'}")

        # report exceptions
        if call.excinfo:
            exc_info = self.build_exception_info(fullname, call.excinfo.type, call.excinfo.value, getattr(call.excinfo.traceback[-1], "_rawentry"))

            if (exc_info and exc_info not in (self.test_result_data[fullname].get("comment", None) or "") and (call.excinfo.type is not pytest.skip.Exception)
                    and not skip_status):
                self.test_result_data[fullname]["comment"] = "".join((self.test_result_data[fullname].get("comment", None) or "", html_row("failed", exc_info)))

        self._build_report_description(item, call, report, skip_status)

        report.user_properties.append(("report", self.report[fullname]))

        if not getattr(item.config.option, "adaptavist", False):
            # adaptavist reporting disabled: no need to proceed here
            return

        if marker := item.get_closest_marker("testcase"):
            test_case_key = marker.kwargs["test_case_key"]
            test_step_key = int(marker.kwargs["test_step_key"]) if marker.kwargs["test_step_key"] else None
            self.create_report(test_case_key,
                               test_step_key or None,
                               call.stop - call.start,
                               skip_status,
                               report.passed,
                               self.test_result_data[fullname],
                               get_spec(fullname))

    def _setup_report(self, worker_input: dict[str, Any]):
        """
        Setup adaptavist report.

        Creates a new test run (and test plan) if needed as follows:
            * If test run key is specified then report to that one
            * Else if a test plan suffix is specified, create a new test plan (if not yet existing) and a new test run linked to that
            * Else if test plan key is given, create a new test run linked to that test plan
            * Else create a new test run just for given project

        Apart from that, a new test plan is created if the given test plan suffix does not match any existing test plan.
        Finally, both test plan and test run are interconnected.

        Naming convention:
            * New test plans are named like "<project key> <test plan suffix>" (where test plan suffix must be unique)
            * New test runs are named like "<test plan name or project key> <test run suffix> <datetime now>"
        """
        test_run_name = self._eval_format(str(self.config.getini("test_run_name")))
        test_plan_name = self._eval_format(str(self.config.getini("test_plan_name")))

        if self.project_key:
            if not self.test_plan_key and self.test_plan_suffix:
                test_plans = self.adaptavist.get_test_plans(f'projectKey = "{self.project_key}"')

                self.test_plan_key = ([test_plan["key"] for test_plan in test_plans if test_plan["name"] == test_plan_name]
                                      or [test_plan["key"] for test_plan in test_plans if test_plan["name"].endswith(self.test_plan_suffix)] or [None])[0]

                if not self.test_plan_key:
                    self.test_plan_key = self.adaptavist.create_test_plan(project_key=self.project_key,
                                                                          test_plan_name=test_plan_name,
                                                                          folder=self.test_plan_folder)

            if not self.test_run_key:
                test_plan_name = self.adaptavist.get_test_plan(test_plan_key=self.test_plan_key).get("name", None) if self.test_plan_key else ""

                # create new test run either in master (normal sequential mode) or worker0 (load balanced mode) only or - if requested - in each worker
                distribution = worker_input.get("options", {}).get("dist", None)
                if not worker_input or (worker_input.get("workerid", "gw0") in [None, "gw0"]) or (distribution == "each"):
                    self.test_run_key = self.adaptavist.get_test_run_by_name(test_run_name).get("key", None) if (distribution != "each") else ""
                    test_run_name += f" {worker_input.get('workerid', 'gw0').split('gw')[1]}" if (
                        distribution == "each" and (not self.test_environment or self.test_environment not in test_run_name)) else ""

                    if not self.test_run_key:
                        self.test_run_key = self.adaptavist.create_test_run(project_key=self.project_key,
                                                                            test_plan_key=self.test_plan_key,
                                                                            test_run_name=test_run_name,
                                                                            test_cases=self.test_case_keys,
                                                                            folder=self.test_run_folder) or ""

                        self.test_refresh_info[self.test_run_key] = self.test_plan_key

                        # mark test case key to be able to decide whether to use existing test result or to create a new one
                        for test_case_key in self.test_case_keys or []:
                            # only mark the first one (e.g. in case of parametrized or repeated methods)
                            key = next((key for key in self.test_refresh_info if re.search(test_case_key + r"[ \[\b]", key)), test_case_key)
                            self.test_refresh_info[key] = self.test_run_key

                elif worker_input and (worker_input.get("workerid", "gw0") not in [None, "gw0"]):
                    # let other workers (if any) wait until test run is available
                    found: dict[str, Any] = {}
                    while not found:
                        time.sleep(1)
                        found = self.adaptavist.get_test_run_by_name(test_run_name)

                    self.test_run_key = found.get("key", None)

            # connect test plan and test run if not yet done
            if self.test_plan_key and self.test_refresh_info.get(self.test_run_key, None) != self.test_plan_key:
                self.adaptavist.edit_test_plan(test_plan_key=self.test_plan_key, test_runs=[self.test_run_key])

                self.test_refresh_info[self.test_run_key] = self.test_plan_key

        # create new environment key if needed
        if self.test_case_keys and self.test_environment:
            project_key = self.adaptavist.get_test_run(self.test_run_key).get("projectKey", None) if self.test_run_key else self.project_key
            # if getpass.getuser().lower() != "jenkins" and not pytest.test_environment.endswith("(local system)"):
            #     pytest.test_environment = pytest.test_environment.strip() + " (local system)"
            if self.test_environment not in [environment["name"] for environment in self.adaptavist.get_environments(project_key)]:
                self.adaptavist.create_environment(project_key, self.test_environment)

    @pytest.hookimpl(trylast=True)
    def pytest_unconfigure(self, config: Config):  # pylint: disable=unused-argument
        """This is called before test process is exited."""

        # create and output Adaptavist test cycle information
        if not self.enabled or not self.reporter:
            return

        self.reporter.section("ATM test cycle info", bold=True)

        self.reporter.line(f"project_key:   {getattr(self, 'project_key', None)}")
        self.reporter.line(f"test_plan_key: {getattr(self, 'test_plan_key', None)}")
        self.reporter.line(f"test_run_key:  {getattr(self, 'test_run_key', None)}")
        if getattr(self, "test_run_keys", None) and getattr(self, "test_run_keys", [None]) != [getattr(self, "test_run_key", None)]:
            self.reporter.line(f"cycle_key(s):  {', '.join(self.test_run_keys)}")

        traceability = None
        test_summary = None
        score_matrix = None
        if (base_url := ATMConfiguration().get("jira_server", "")) and getattr(self, "project_key", None) and getattr(self, "test_run_key", None):
            # pylint: disable=line-too-long
            cycle_string = "%22%2C%20%22".join(self.test_run_keys) if getattr(self, "test_run_keys", None) else self.test_run_key or ""
            traceability = f"{base_url}/secure/Tests.jspa#/reports/traceability/report/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TRACEABILITY_REPORT.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"  # noqa
            test_summary = f"{base_url}/secure/Tests.jspa#/reports/testresults/board/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_BOARD.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"  # noqa
            score_matrix = f"{base_url}/secure/Tests.jspa#/reports/testresults/scorecard/coverage/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_SCORECARD_BY_COVERAGE.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"  # noqa

        self.reporter.line(f"traceability:  {traceability}")
        self.reporter.line(f"test_summary:  {test_summary}")
        self.reporter.line(f"score_matrix:  {score_matrix}")

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int):
        """This is called after whole test run has finished."""

        yield

        if hasattr(session.config, "workerinput") or not self.enabled:
            return

        # create and output final status line (used by jenkins pipeline)
        exceptions_raised = 0
        high_prios_failed = 0

        not_built = True
        for value in self.report.values():
            exceptions_raised += 1 if value["exc_info"] else 0
            high_prios_failed += 1 if value["status"] == "failed" and value["priority"] == PRIORITY_HIGH else 0
            not_built = not_built and value["status"] not in ["passed", "failed"]

        if exceptions_raised or high_prios_failed or exitstatus in {3, 4}:
            status = "FAILURE"
        elif exitstatus == 1:
            status = "UNSTABLE"
        elif exitstatus == 2:
            status = "ABORTED"
        elif exitstatus == 5 or not_built:
            status = "NOT_BUILT"
        else:
            status = "SUCCESS"

        line = f"final_status ({status}): {getattr(self, 'project_key', None)}, "
        line += f"{getattr(self, 'test_plan_key', None)}, "
        line += f"{', '.join(getattr(self, 'test_run_keys', []) or [str(getattr(self, 'test_run_key', None))])}, "
        line += f"{high_prios_failed} high prio tc(s) failed, {exceptions_raised} exception(s) raised, exitstatus={exitstatus}"

        colormap = {"ABORTED": "white", "FAILURE": "red", "NOT_BUILT": "white", "SUCCESS": "green", "UNSTABLE": "yellow"}

        markup = {colormap[status]: True, "bold": True}

        if self.reporter:
            self.reporter.write_sep("=", title=None, fullwidth=None, **markup)
            self.reporter.write_line(line, **markup)
            self.reporter.write_sep("=", title=None, fullwidth=None, **markup)

    def _create_item_collection(self, items: list[pytest.Item], collected_project_keys: list[str], collected_items: dict[str, list[pytest.Function]]):
        """Create the list of test methods to be executed and included in adaptavist report."""
        if not self.enabled or not self.project_key and not self.test_run_key:
            return

        if self.test_case_keys:
            # add any specified test cases, even if they are not implemented
            collected_items.update({key: [] for key in self.test_case_keys if key not in collected_items})

        # build and order the list of items to be executed and included in adaptavist report
        if not self.test_run_key:
            # only include those test cases that are part of collected projects (including test database)
            search_mask = f"""projectKey IN ("{'", "'.join(collected_project_keys + ["TEST"])}")"""
            test_cases = [test_case["key"] for test_case in self.adaptavist.get_test_cases(search_mask=search_mask)] if items else list(collected_items.keys())
        else:
            # only include those test cases that are part of this test run
            test_run = self.adaptavist.get_test_run(self.test_run_key)
            test_cases = [item["testCaseKey"] for item in test_run.get("items", [])]

        # define the execution order for all test cases (specified first, followed by the rest)
        if not self.test_case_order:
            self.test_case_order = test_cases if self.test_run_key else self.test_case_keys

        # order items and test cases
        ordered_collected_items = collected_items
        if self.test_case_order or self.test_case_range:
            ordered_collected_items = {key: collected_items[key] for key in self.test_case_order if key in collected_items}
            ordered_collected_items.update({key: collected_items[key] for key in collected_items if key not in ordered_collected_items})
            ordered_collected_items = apply_test_case_range(ordered_collected_items, self.test_case_range)
            ordered_items: list[pytest.Function | pytest.Item] = [item for sublist in ordered_collected_items.values() for item in sublist]
            ordered_items.extend([item for item in items if item not in ordered_items])
            items[:] = ordered_items

        # define the list of test cases to be included in adaptavist report
        # (intersection of collected pytest cases and existing test cases)
        self.test_case_keys = intersection(list(ordered_collected_items.keys()), test_cases)

    def _setup_item_collection(self, items: list[pytest.Item], collected_project_keys: list[str], collected_items: dict[str, list[pytest.Item]]):
        """Setup and prepare collection of available test methods."""

        # define the test case keys to be processed
        test_case_keys = self.test_case_keys

        if self.test_run_key:
            test_run = self.adaptavist.get_test_run(self.test_run_key)
            test_cases = [item["testCaseKey"] for item in test_run.get("items", [])]

            # if test case keys are specified as well, take the intersection of both (if empty then all methods are skipped)
            test_case_keys = intersection(self.test_case_keys, test_cases) or [None] if self.test_case_keys else test_cases

        # run over all found test methods and collect the relevant
        for item in items:
            fullname = get_item_nodeid(item)
            # initialize item's status info
            self.item_status_info[fullname] = {}
            # initialize item's test result data (see meta_data function down below)
            self.test_result_data[fullname] = {"comment": None, "attachment": None}

            # check for valid test case method signature test_[<project>_]T<test case>[_<test step>]
            # (project key and step index are optional)
            if result := re.search("^test_(([A-Z]+[A-Z0-9_]*[^_])_)?(T[1-9]+[0-9]*)(_([1-9]+[0-9]*))*", item.name, re.IGNORECASE):
                _, project_key, test_case_key, _, test_step_key = result.groups()

                if not project_key:
                    project_key = getattr(item.cls, "project_key", None)  # type:ignore

                    if marker := item.get_closest_marker("project"):
                        project_key = marker.kwargs["project_key"]

                if not project_key:
                    project_key = self.project_key or "TEST"

                if project_key not in collected_project_keys:
                    collected_project_keys.append(project_key)

                # initialize refresh info
                specs = get_spec(fullname)
                self.test_refresh_info[project_key + "-" + test_case_key + (specs or "")] = None

                # mark this item with appropriate info (easier to read from when creating test results)
                if (project_key + "-" + test_case_key) in test_case_keys or not test_case_keys:
                    item.add_marker(pytest.mark.testcase(project_key=project_key, test_case_key=project_key + "-" + test_case_key, test_step_key=test_step_key))
                if (test_case_keys and (project_key + "-" + test_case_key) not in test_case_keys):
                    item.add_marker(pytest.mark.skip(reason="skipped as requested"))
                else:
                    collected_items.setdefault(project_key + "-" + test_case_key, []).append(item)
            elif self.cfg.get_bool("skip_ntc_methods", False):
                # skip methods that are no test case methods
                item.add_marker(pytest.mark.skip)

    def _eval_format(self, string: str) -> str:
        """Evaluate configured test_run_name or test_plan_name setting."""
        try:
            placeholders: list[str] = self._ATTRIBUTE_PLACEHOLDERS.findall(string)
            pytest_adaptavist_variables: list[str] = []
            for placeholder in placeholders:
                pytest_adaptavist_variables.append(getattr(self, placeholder))
            string = self._ATTRIBUTE_REPLACEMENT.sub("{}", string)
            return string.format(*pytest_adaptavist_variables)
        except AttributeError:
            pytest.exit(f"Invalid test_run_name or test_plan_name configured: '{placeholder}' not known.", returncode=6)


class AdaptavistAssumption(Assumption):
    """Inherited assumption object extended with a line number attribute."""

    def __init__(self, entry: str, tb: FrameType, locals: list[str] | None = None):  # pylint: disable=redefined-builtin
        self.line_no = tb.f_lineno
        super().__init__(entry, tb, locals)


def is_unexpected_exception(exc_type: Exception) -> bool:
    """Check if exception type is unexpected (any exception except AssertionError, pytest.block.Exception, pytest.skip.Exception)."""
    if exc_type and (isinstance(exc_type, (Exception, BaseException)) or issubclass(exc_type, (Exception, BaseException))):
        return exc_type not in (None, FailedAssumption, AssertionError, pytest.block.Exception, pytest.skip.Exception)  # type: ignore
    return False
