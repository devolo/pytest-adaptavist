import inspect
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.mark.structures import MarkDecorator
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.terminal import TerminalReporter
from adaptavist import Adaptavist
from adaptavist.const import PRIORITY_HIGH, STATUS_BLOCKED, STATUS_FAIL, STATUS_NOT_EXECUTED, STATUS_PASS

from ._atm_configuration import ATMConfiguration
from ._helpers import (apply_test_case_range,
                       calc_test_result_status,
                       get_item_name_and_spec,
                       get_item_nodeid,
                       get_marker,
                       handle_failed_assumptions,
                       html_row,
                       import_module,
                       intersection)


class PytestAdaptavist:

    def __init__(self, config: Config):
        self.config = config
        # dictionary to store temporal info about test items
        self.item_status_info: Dict[str, Any] = {}
        # dictionary to control whether to create new or to update existing test results
        self.test_refresh_info: Dict[str, Any] = {}
        # to be able to store data inside of test methods (see meta_data function down below)
        self.test_result_data: Dict[str, Any] = {}
        # dictionary to store final report
        self.report: Dict[str, Any] = {}
        self.project_key = None

        self.test_case_key = None
        self.test_run_keys: List[str] = []
        self.items = None
        self.adaptavist = None
        self.reporter: TerminalReporter = config.pluginmanager.getplugin("terminalreporter")
        self.build_url = ""
        self.code_base = ""
        self.test_plan_key = ""
        self.test_run_key = ""
        self.test_case_order: List[str] = []
        self.test_case_keys: List[str] = []
        self.test_environment: List[str] = []
        self.test_case_range: List[str] = []
        self.test_plan_folder: str = ""
        self.test_run_folder: str = ""
        self.test_plan_suffix: str = ""
        self.test_run_suffix: str = ""
        self.atm_configure(config)

    def pytest_runtest_logreport(self, report: TestReport):
        """"""

        user_properties = dict(report.user_properties)

        if user_properties.get("atmcfg"):
            self.test_plan_key = user_properties["atmcfg"].get("test_plan_key", None)
            self.project_key = user_properties["atmcfg"].get("project_key", None)
            self.test_run_key = user_properties["atmcfg"].get("test_run_key", None)
            if self.test_run_key and self.test_run_key not in self.test_run_keys:
                self.test_run_keys.append(self.test_run_key)

    def create_item_collection(self, items: List[Item], collected_project_keys: List[str], collected_items: Dict):
        """Create the list of test methods to be executed and included in adaptavist report."""

        if self.adaptavist and (self.project_key or self.test_run_key):
            if self.test_case_keys:
                # add any specified test cases, even if they are not implemented
                collected_items.update({key: [] for key in self.test_case_keys if key not in collected_items})

            # build and order the list of items to be executed and included in adaptavist report
            if not self.test_run_key:
                # only include those test cases that are part of collected projects (including test database)
                search_mask = f"""projectKey IN ("{'", "'.join(collected_project_keys + ["TEST"])}")"""
                test_cases = [test_case["key"] for test_case in self.adaptavist.get_test_cases(
                    search_mask=search_mask)] if items and getattr(items[0].config.option, "adaptavist") else collected_items.keys()
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
                ordered_items = [item for sublist in ordered_collected_items.values() for item in sublist]
                ordered_items.extend([item for item in items if item not in ordered_items])
                items[:] = ordered_items

            # define the list of test cases to be included in adaptavist report
            # (intersection of collected pytest cases and existing test cases)
            self.test_case_keys = intersection(list(ordered_collected_items.keys()), test_cases)

        self.items = items  # for later usage

    def atm_configure(self, config: Config) -> bool:
        """Setup adaptavist reporting based on given requirements (config)."""
        cfg = ATMConfiguration()

        if not self.adaptavist:
            self.adaptavist = Adaptavist(cfg.get("jira_server", ""), cfg.get("jira_username", ""), cfg.get("jira_password", ""))
        if not self.project_key:
            self.project_key = cfg.get("project_key", None)

        # support of multiple environments
        # in case of using xdist's "each" mode, a test run for each specified environment is created
        # and test_environment can be used (when given as a list or comma-separated string) to specify keys for each test run resp. worker node
        worker_input = getattr(config, "workerinput", {})
        distribution = worker_input.get("options", {}).get("dist", None)
        index = int(worker_input.get("workerid", "gw0").split("gw")[1]) if (distribution == "each") else 0

        entry = self.test_environment or cfg.get("test_environment", []) or []
        test_environments = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry
        self.test_environment = test_environments[index if index < len(test_environments) else -1] if test_environments else None

        entry = self.test_case_keys or cfg.get("test_case_keys", []) or []
        self.test_case_keys = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        entry = self.test_case_order or cfg.get("test_case_order", []) or []
        self.test_case_order = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        entry = self.test_case_range or cfg.get("test_case_range", []) or []
        self.test_case_range = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

        if not self.test_plan_key:
            self.test_plan_key = cfg.get("test_plan_key", None)
        if not self.test_plan_folder:
            self.test_plan_folder = cfg.get("test_plan_folder", None)
        if not self.test_plan_suffix:
            self.test_plan_suffix = cfg.get("test_plan_suffix", None)
        if not self.test_run_key:
            self.test_run_key = cfg.get("test_run_key", None)
        if not self.test_run_folder:
            self.test_run_folder = cfg.get("test_run_folder", None)
        if not self.test_run_suffix:
            self.test_run_suffix = cfg.get("test_run_suffix", "test run " + datetime.now().strftime("%Y%m%d%H%M"))
        if getattr(pytest, "skip_ntc_methods", None) is None:
            self.skip_ntc_methods = cfg.get_bool("skip_ntc_methods", False)

        return True

    def setup_item_collection(self, items: List[Item], collected_project_keys: List[str], collected_items: Dict):
        """Setup and prepare collection of available test methods."""

        # define the test case keys to be processed
        test_case_keys = self.test_case_keys

        if self.test_case_key:
            test_run = self.adaptavist.get_test_run(self.test_run_key)
            test_cases = [item["testCaseKey"] for item in test_run.get("items", [])]

            # if test case keys are specified as well, take the intersection of both (if empty then all methods are skipped)
            test_case_keys = intersection(self.test_case_keys, test_cases) or [None] if self.test_case_keys else test_cases

        # run over all found test methods and collect the relevant
        for item in items:
            item.fullname = get_item_nodeid(item)
            # initialize item's status info
            self.item_status_info[item.fullname] = {}
            # initialize item's test result data (see meta_data function down below)
            self.test_result_data[item.fullname] = {"comment": None, "attachment": None}

            # check for valid test case method signature test_[<project>_]T<test case>[_<test step>]
            # (project key and step index are optional)
            result = re.search("^test_(([A-Z]+[A-Z0-9_]*[^_])_)?(T[1-9]+[0-9]*)(_([1-9]+[0-9]*))*", item.name, re.IGNORECASE)
            if result:
                _, project_key, test_case_key, _, test_step_key = result.groups()

                if not project_key:
                    project_key = getattr(item.cls, "project_key", None)

                    marker = get_marker(item, "project")
                    if marker is not None:
                        project_key = marker.kwargs["project_key"]

                if not project_key:
                    project_key = self.project_key or "TEST"

                if project_key not in collected_project_keys:
                    collected_project_keys.append(project_key)

                # initialize refresh info
                _, specs = get_item_name_and_spec(get_item_nodeid(item))
                self.test_refresh_info[project_key + "-" + test_case_key + (specs or "")] = None

                # mark this item with appropriate info (easier to read from when creating test results)
                item.add_marker(pytest.mark.testcase(project_key=project_key, test_case_key=project_key + "-" + test_case_key, test_step_key=test_step_key))

                if (test_case_keys and (project_key + "-" + test_case_key) not in test_case_keys):
                    item.add_marker(pytest.mark.skip(reason="skipped as requested"))
                else:
                    collected_items.setdefault(project_key + "-" + test_case_key, []).append(item)
            elif self.skip_ntc_methods:
                # skip methods that are no test case methods
                item.add_marker(pytest.mark.skip)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session: Session, config: Config, items: List[Item]):  # pylint: disable=unused-argument
        """Collect items matching given requirements (config)
        and prepare adaptavist reporting.

            The following parameters need to be set before (e.g. either in pytest names or as class member):
            :param pytest.project_key: to create a new test run
            :param pytest.test_run_key: to use existing test run
            :param pytest.test_run_suffix: as option when creating new test run (e.g. to specify release version etc.)
            :param pytest.test_case_keys: as option to run only a subset of implemented test cases
        """
        for item in items:
            item.fullname = get_item_nodeid(item)
            # initialize item's status info
            self.item_status_info[item.fullname] = {}
            # initialize item's test result data (see meta_data function down below)
            self.test_result_data[item.fullname] = {"comment": None, "attachment": None}

        # store items for later usage
        self.items = items

        if not self.atm_configure(config):
            return

        collected_project_keys = []
        collected_items = {}

        self.setup_item_collection(items, collected_project_keys, collected_items)
        self.create_item_collection(items, collected_project_keys, collected_items)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: Item):
        """This is called before calling the test item (i.e. before any parameter/fixture call).

            Used to skip test items dynamically (e.g. triggered by some other item or control function).
        """
        skip_status = get_marker(item, "block") or get_marker(item, "skip")

        if skip_status:
            skip_reason = skip_status.kwargs.get("reason", "")
            if not skip_reason and self.test_result_data[item.fullname].get("blocked") is True:
                skip_reason = self.test_result_data[item.fullname].get("comment", "")

            pytest.skip(msg=skip_reason)

    def create_report(self,
                      test_case_key: str,
                      test_step_key: Optional[str],
                      execute_time: float,
                      skip_status: Optional[bool],
                      passed: bool,
                      test_result_data: Dict[str, Any],
                      specs=None):
        """Generate adaptavist test results for given item.

            :param test_case_key: The test case to report.
            :param test_step_key: The test step to report.
            :param execute_time: The time spent for execution.
            :param skip_status: pytest marker, may hold either a pytest.mark.skip or pytest.mark.block
            :param passed: True or False, depending on test result.
            :param test_result_data: additional data containing comments, attachments, etc.
        """
        test_run_key = self.test_run_key

        if not (test_run_key or test_case_key in (self.test_case_key or [])):
            return

        adaptavist = self.adaptavist

        test_result = adaptavist.get_test_result(test_run_key, test_case_key)

        if not test_result or self.test_refresh_info[test_case_key + (specs or "")] != test_run_key:
            # create new test result to prevent accumulation of data
            # when using an existing test run key multiple times
            adaptavist.create_test_result(test_run_key=test_run_key, test_case_key=test_case_key, environment=self.test_environment, status=None)

            # refetch result
            test_result = adaptavist.get_test_result(test_run_key, test_case_key)

            self.test_refresh_info[test_case_key + (specs or "")] = test_run_key

        # touch parametrized/repeated items
        for key in self.test_refresh_info:
            if re.search(test_case_key + r"[ \[\b]", key):
                self.test_refresh_info[key] = self.test_run_key

        # get optional meta data (comments, attachments) of test case method
        comment = skip_status.kwargs.get("reason") if skip_status else test_result_data.get("comment")
        description = None if skip_status else test_result_data.get("description")
        attachment = None if skip_status else test_result_data.get("attachment")

        now = datetime.now().strftime('%Y%m%d%H%M')
        header = f"---------------------------------------- {now} ----------------------------------------" if specs else ""

        if not skip_status and not test_step_key:
            # update test case with CI related info
            adaptavist.edit_test_case(test_case_key,
                                      labels=["automated"],
                                      build_urls=[f"<a href=\"{self.build_url}\">{self.build_url}</a>" if self.build_url else ""],
                                      code_bases=[f"<a href=\"{self.code_base}\">{self.code_base}</a>" if self.code_base else ""])

        if test_step_key:

            # in case of parameterization or repetition the status will be Fail if one iteration failed
            last_result = next((result for result in test_result.get("scriptResults", []) if result["index"] == int(test_step_key) - 1), {})

            if skip_status and last_result.get("status", None) != STATUS_FAIL:
                status = STATUS_BLOCKED if skip_status.name == "block" else STATUS_NOT_EXECUTED
            else:
                status = STATUS_PASS if passed and last_result.get("status") != STATUS_FAIL else STATUS_FAIL

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + (last_result.get("comment", "") if specs else "")

            adaptavist.edit_test_script_status(test_run_key=test_run_key,
                                               test_case_key=test_case_key,
                                               step=int(test_step_key),
                                               environment=self.test_environment,
                                               status=status,
                                               comment=comments if (specs or last_result.get("status") != STATUS_FAIL) else None)

            if attachment:
                adaptavist.add_test_script_attachment(test_run_key=test_run_key,
                                                      test_case_key=test_case_key,
                                                      step=int(test_step_key),
                                                      attachment=attachment,
                                                      filename=test_result_data.get("filename"))

            # adjust parent test result status according to current test script results
            test_result = adaptavist.get_test_result(test_run_key, test_case_key)
            status = calc_test_result_status(test_result.get("scriptResults", []))

            comments = ""
            if skip_status:
                # modify comment to add info about blocked or skipped script steps
                comments = f'step {test_step_key} {"blocked" if skip_status.name == "block" else "skipped"}{("<br>" + comment + "<br>") if comment else ""}'
            elif not passed:
                # modify comment to add info about failure in script steps
                comments = f'step {test_step_key}{("<br>" + comment + "<br>") if comment else ""} failed:'

            # find the right position to insert comments of this test execution (in case of parametrized or repeated test methods)
            index = test_result.get("comment", "").find("---------------------------------------- ")

            adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                               test_case_key=test_case_key,
                                               environment=self.test_environment,
                                               status=status,
                                               comment=(test_result.get("comment", "") + comments) if index < 0 else
                                               (test_result.get("comment", "")[:index] + comments + test_result.get("comment", "")[index:]),
                                               execute_time=execute_time)

        else:
            # change parent test result status only if blocked or failed or if there was no previous failure
            status = test_result.get("status", STATUS_NOT_EXECUTED)
            if status == STATUS_NOT_EXECUTED and skip_status:
                status = STATUS_BLOCKED if skip_status.name == "block" else STATUS_NOT_EXECUTED
            elif status == STATUS_FAIL or (not passed and not skip_status):
                status = STATUS_FAIL
            elif status == STATUS_NOT_EXECUTED:
                status = STATUS_PASS if passed else STATUS_FAIL

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + test_result.get("comment", "")

            adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                               test_case_key=test_case_key,
                                               environment=self.test_environment,
                                               status=status,
                                               comment=comments,
                                               execute_time=execute_time)

            if attachment:
                self.adaptavist.add_test_result_attachment(test_run_key=test_run_key,
                                                           test_case_key=test_case_key,
                                                           attachment=attachment,
                                                           filename=test_result_data.get("filename"))

    def build_report_description(self, item: Item, call: CallInfo, report: TestReport, skip_status: MarkDecorator):
        """Generate standard test results for given item.
            :param item: The item to report.
                :param call: The call info object.
                :param report: The report object.
                :param skip_status: pytest marker, may hold either a pytest.mark.skip or pytest.mark.block
        """
        report.description = (skip_status.kwargs.get("reason", None) if skip_status else "") or self.test_result_data[item.fullname].get("comment", None) or ""

        if call.when != "teardown" or call.excinfo:
            test_case_key = None
            test_case_name = None
            priority = None
            marker = get_marker(item, "testcase")
            if marker is not None:
                test_case_key = marker.kwargs["test_case_key"]
                if test_case_key in (self.test_case_keys or []):
                    test_case_info = self.adaptavist.get_test_case(test_case_key)
                    test_case_name = test_case_info.get("name", None)
                    priority = test_case_info.get("priority", None)

            if (not (call.excinfo and call.excinfo.type is pytest.skip.Exception) and not skip_status and test_case_key):
                subkeys = [key for key in self.test_result_data if key != item.fullname and key.startswith(item.fullname)]
                for key in subkeys:
                    report.description = "<br>".join((report.description,
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
                "details": report.description or "",
                "exc_info": is_unexpected_exception(self.item_status_info[item.fullname].get("exc_info", (None, None, None))[0])
            }

    def build_exception_info(self, item_name, exc_type, exc_value, traceback):
        """Generate description info about exceptions."""

        exc_info = None

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

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item: Item, call: CallInfo):
        """This is called at setup, run/call and teardown of test items.

            Generates adaptavist test run results from test reports.
        """
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
        report.user_properties.append(("docstr", inspect.cleandoc(item.obj.__doc__ or "")))

        if call.when not in ("call", "setup"):
            return

        skip_status = get_marker(item, "block") or get_marker(item, "skip")

        if call.when == "setup":
            if getattr(item.config.option, "adaptavist", False):
                # setup report only if adaptavist reporting is enabled
                self.setup_report(getattr(item.config, "workerinput", {}))
                for user_property in report.user_properties:
                    if user_property[0] == "atmcfg":
                        del user_property[1]["test_environment"]
            if (not call.excinfo and not skip_status and self.test_result_data[item.fullname].get("blocked", None) is not True):
                # no skipped or blocked methods to report
                return

        # if method was blocked dynamically (during call) an appropriate marker is used
        # to handle the reporting in the same way as for statically blocked methods
        # (status will be reported as "Blocked" with given comment in Adaptavist)
        if not skip_status and (call.excinfo and call.excinfo.type in (pytest.block.Exception, pytest.skip.Exception)
                                or not call.excinfo and self.test_result_data[item.fullname].get("blocked", None) is True):
            reason = self.test_result_data[item.fullname].get("comment", None) or (str(
                call.excinfo.value).partition("\n")[0] if call.excinfo and call.excinfo.type in (pytest.block.Exception, pytest.skip.Exception) else "")
            skip_status = pytest.mark.block(reason=reason) if ((call.excinfo and call.excinfo.type is pytest.block.Exception)
                                                               or self.test_result_data[item.fullname].get("blocked", None) is True) else pytest.mark.skip(
                                                                   reason=reason)
            if report.outcome != "skipped":
                report.outcome = "skipped"  # to mark this as SKIPPED in pytest reports
                report.longrepr = (__file__,
                                   getattr(sys, "_getframe")().f_lineno if hasattr(sys, "_getframe") else None,
                                   f"Skipped: {reason or 'blocked dynamically or partially'}")

        # report exceptions
        if call.excinfo:
            exc_info = self.build_exception_info(item.fullname, call.excinfo.type, call.excinfo.value, getattr(call.excinfo.traceback[-1], "_rawentry"))

            if (exc_info and exc_info not in (self.test_result_data[item.fullname].get("comment", None) or "")
                    and (call.excinfo.type is not pytest.skip.Exception) and not skip_status):
                self.test_result_data[item.fullname]["comment"] = "".join(
                    (self.test_result_data[item.fullname].get("comment", None) or "", html_row(False, exc_info)))

        # handling failed assumptions
        handle_failed_assumptions(item, call, report)

        self.build_report_description(item, call, report, skip_status)

        # build_terminal_report(when="call", item=item, status=report.outcome if not skip_status else ("blocked" if skip_status.name == "block" else "skipped"))

        report.user_properties.append(("report", self.report[get_item_nodeid(item)]))

        if not getattr(item.config.option, "adaptavist", False):
            # adaptavist reporting disabled: no need to proceed here
            return

        if self.test_result_data[item.fullname].get("done", False):
            # this item has been reported already within a meta block context (see below)
            return

        marker = get_marker(item, "testcase")
        if marker is not None:

            test_case_key = marker.kwargs["test_case_key"]
            test_step_key = marker.kwargs["test_step_key"]

            _, specs = get_item_name_and_spec(get_item_nodeid(item))
            self.create_report(test_case_key, test_step_key, call.stop - call.start, skip_status, report.passed, self.test_result_data[item.fullname], specs)

    def setup_report(self, worker_input):
        """Setup adaptavist report.

            Creates a new test run (and test plan) if needed as follows:
            * if test run key is specified then report to that one
            * else if a test plan suffix is specified, create a new test plan (if not yet existing) and a new test run linked to that
            * else if test plan key is given, create a new test run linked to that test plan
            * else create a new test run just for given project

            Apart from that, a new test plan is created if the given test plan suffix does not match any existing test plan.
            Finally, both test plan and test run are interconnected.

            naming convention:
            new test plans are named like "<project key> <test plan suffix>" (where test plan suffix must be unique)
            new test runs are named like "<test plan name or project key> <test run suffix> <datetime now>"
        """

        if self.project_key and self.test_case_keys:
            if not self.test_plan_key and self.test_plan_suffix:
                test_plan_name = f"{self.project_key} {self.test_plan_suffix}"
                test_plans = self.adaptavist.get_test_plans(f'projectKey = "{self.project_key}"')

                self.test_plan_key = ([test_plan["key"] for test_plan in test_plans if test_plan["name"] == test_plan_name]
                                      or [test_plan["key"] for test_plan in test_plans if test_plan["name"].endswith(self.test_plan_suffix)] or [None])[0]

                if not self.test_plan_key:
                    self.test_plan_key = self.adaptavist.create_test_plan(project_key=self.project_key,
                                                                          test_plan_name=test_plan_name,
                                                                          folder=self.test_plan_folder)

            if not self.test_run_key:
                test_plan_name = self.adaptavist.get_test_plan(test_plan_key=self.test_plan_key).get("name", None) if self.test_plan_key else None
                test_run_name = f"{test_plan_name or self.project_key} {self.test_run_suffix}"

                # create new test run either in master (normal sequential mode) or worker0 (load balanced mode) only or - if requested - in each worker
                distribution = worker_input.get("options", {}).get("dist", None)
                if not worker_input or (worker_input.get("workerid", "gw0") in [None, "gw0"]) or (distribution == "each"):
                    self.test_run_key = self.adaptavist.get_test_run_by_name(test_run_name).get("key", None) if (distribution != "each") else None
                    test_run_name += f" {worker_input.get('workerid', 'gw0').split('gw')[1]}" if (
                        distribution == "each" and (not self.test_environment or self.test_environment not in test_run_name)) else ""

                    if not self.test_run_key:
                        self.test_run_key = self.adaptavist.create_test_run(project_key=self.project_key,
                                                                            test_plan_key=self.test_plan_key,
                                                                            test_run_name=test_run_name,
                                                                            test_cases=self.test_case_keys,
                                                                            folder=self.test_run_folder)

                        self.test_refresh_info[self.test_run_key] = self.test_plan_key

                        # mark test case key to be able to decide whether to use existing test result or to create a new one
                        for test_case_key in self.test_case_keys or []:
                            # only mark the first one (e.g. in case of parametrized or repeated methods)
                            key = next((key for key in self.test_refresh_info if re.search(test_case_key + r"[ \[\b]", key)), test_case_key)
                            self.test_refresh_info[key] = self.test_run_key

                elif worker_input and (worker_input.get("workerid", "gw0") not in [None, "gw0"]):
                    # let other workers (if any) wait until test run is available
                    found = {}
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
    def pytest_unconfigure(self, config: Config):
        """This is called before test process is exited."""

        if config.getoption("-h") or config.getoption("--help"):
            return

        # create and output Adaptavist test cycle information
        if getattr(config.option, "adaptavist", False) and self.reporter:

            self.reporter.section("ATM test cycle info", bold=True)

            self.reporter.line("project_key:   %s" % getattr(self, "project_key", None))
            self.reporter.line("test_plan_key: %s" % getattr(self, "test_plan_key", None))
            self.reporter.line("test_run_key:  %s" % getattr(self, "test_run_key", None))
            if getattr(self, "test_run_keys", None) and getattr(self, "test_run_keys", [None]) != [getattr(self, "test_run_key", None)]:
                self.reporter.line("cycle_key(s):  %s" % ", ".join(self.test_run_keys))

            traceability = None
            test_summary = None
            score_matrix = None
            base_url = ATMConfiguration().get("jira_server", "")
            if base_url and getattr(self, "project_key", None) and getattr(self, "test_run_key", None):
                # pylint: disable=line-too-long
                cycle_string = "%22%2C%20%22".join(self.test_run_keys) if getattr(self, "test_run_keys", None) else self.test_run_key or ""
                traceability = f"{base_url}/secure/Tests.jspa#/reports/traceability/report/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TRACEABILITY_REPORT.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"
                test_summary = f"{base_url}/secure/Tests.jspa#/reports/testresults/board/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_BOARD.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"
                score_matrix = f"{base_url}/secure/Tests.jspa#/reports/testresults/scorecard/coverage/view?tql=testResult.projectKey%20IN%20%28%22{self.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_SCORECARD_BY_COVERAGE.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"

            self.reporter.line("traceability:  %s" % traceability)
            self.reporter.line("test_summary:  %s" % test_summary)
            self.reporter.line("score_matrix:  %s" % score_matrix)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_sessionfinish(self, session: Session, exitstatus: int):
        """This is called after whole test run has finished."""

        yield

        if hasattr(session.config, "workerinput"):
            return

        # create and output final status line (used by jenkins pipeline)
        exceptions_raised = 0
        high_prios_failed = 0

        report = self.report

        not_built = True
        for value in report.values():
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
            self.reporter.write_sep("=", **markup)
            self.reporter.write_line(line, **markup)
            self.reporter.write_sep("=", **markup)


def is_unexpected_exception(exc_type: Exception) -> bool:
    """Check if exception type is unexpected (any exception except AssertionError, pytest.block.Exception, pytest.skip.Exception)."""

    if exc_type and (isinstance(exc_type, (Exception, BaseException)) or issubclass(exc_type, (Exception, BaseException))):
        # the following lines are necessary to support 2.x versions of pytest-assume which raise FailedAssumption exceptions on failed assumptions
        pytest_assume = import_module("pytest_assume")
        failed_assumption = pytest_assume.plugin.FailedAssumption if pytest_assume and hasattr(pytest_assume, "plugin") and hasattr(
            pytest_assume.plugin, "FailedAssumption") else None
        return exc_type not in (None, failed_assumption, AssertionError, pytest.skip.Exception)
    return False
