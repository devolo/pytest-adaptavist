#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module provides a set of pytest hooks for generating Adaptavist test run results from test reports."""

import getpass
import inspect
import os
import re
import sys
import signal
import logging
from datetime import datetime

from adaptavist import Adaptavist

import pytest

from _pytest.terminal import TerminalReporter

# const to change the default timeout for meta_blocks
META_BLOCK_TIMEOUT=600

class ATMConfiguration:
    """Configuration class to read config parameters (either from env or from "global_config.json")."""

    def __init__(self):
        """Constructor."""
        try:
            import jstyleson as json
        except ImportError:
            import json

        self.config = {}
        config_file_name = os.path.join("config", "global_config.json")
        if os.path.exists(os.path.abspath(config_file_name)):
            with open(config_file_name, "r") as config_file:
                try:
                    self.config.update(json.load(config_file))
                except Exception as ex:
                    raise ValueError("Failed to load config from file \"{0}\"!".format(config_file), ex)

    def get(self, key, default=None):
        """Get value either from environment or from config file."""

        if key.lower().startswith("cfg_"):
            return self.config.get(key, None) or default
        return os.environ.get(key) or os.environ.get(key.upper()) or self.config.get("cfg_" + key, None) or self.config.get(key, None) or default

    def get_bool(self, key, default=None):
        """Get boolean value either from environment or from config file."""

        result = self.get(key=key, default=default)

        if isinstance(result, bool) or result is None:
            return result

        if result.lower() in ["true", "1", "yes"]:
            return True

        if result.lower() in ["false", "0", "no"]:
            return False

        raise ValueError(f"Invalid bool result: {result}")


class ATMTerminalReporter(TerminalReporter):
    """Terminal reporter class used for prettifying terminal output (also used for synchronization of xdist-worker nodes)."""

    def __init__(self, config):
        """Constructor."""

        # dictionary to store final report
        pytest.report = {}

        super().__init__(config)

    def pytest_runtest_logstart(self, nodeid, location):
        """Empty log in pretty mode (will be done during execution, see calls of build_terminal_report())."""

        if not getattr(self.config.option, "pretty", False) and (getattr(self.config.option, "numprocesses", 0) or 0) < 2:
            super().pytest_runtest_logstart(nodeid=nodeid, location=location)
            return

    def pytest_runtest_logreport(self, report):
        """Empty log in pretty mode (will be done during execution, see calls of build_terminal_report())."""

        item_info = getattr(report, "item_info", {})

        worker_node_suffix = f" [{' -> '.join(filter(None, (report.node.gateway.id, item_info['atmcfg'].get('test_environment', None))))}]" if getattr(self.config.option, "dist", None) == "each" and getattr(report, "node") else ""

        if item_info.get("atmcfg", None):
            pytest.project_key = item_info["atmcfg"].get("project_key", None)
            pytest.test_plan_key = item_info["atmcfg"].get("test_plan_key", None)
            pytest.test_run_key = item_info["atmcfg"].get("test_run_key", None)
            if not hasattr(pytest, "test_run_keys"):
                pytest.test_run_keys = []
            if pytest.test_run_key and pytest.test_run_key not in pytest.test_run_keys:
                pytest.test_run_keys.append(pytest.test_run_key)

        if item_info.get("report", {}):
            pytest.report.update({(item_info.get("nodeid", None) or "") + worker_node_suffix: item_info.get("report", {})})

        if not getattr(self.config.option, "pretty", False):
            super().pytest_runtest_logreport(report=report)
            return

        category, _, _ = self.config.hook.pytest_report_teststatus(report=report, config=self.config)
        self.stats.setdefault(category, []).append(report)  # needed for statistics and summary

        if not getattr(self.config.option, "numprocesses", 0):
            # in sequential mode terminal output is produced immediately (see build_terminal_report)
            return

        if report.when == "teardown":
            return

        if report.when == "setup":
            if (getattr(self.config.option, "numprocesses", 0) or 0) < 2:
                title, specs = get_item_name_and_spec(item_info.get("nodeid", None) or "")
                self.line("")
                self.write_sep("-", title, bold=True)
                self.write_line(item_info.get("docstr", None) or "")
                self.write_line("parameterization " + specs if specs else "")

            if not report.skipped:
                return

        if (getattr(self.config.option, "numprocesses", 0) or 0) > 1:
            title, specs = get_item_name_and_spec(item_info.get("nodeid", None) or "")
            self.line("")
            self.write_sep("-", title + worker_node_suffix, bold=True)
            self.write_line(item_info.get("docstr", None) or "")
            self.write_line("parameterization " + specs if specs else "")

        status = item_info.get("report", {}).get("status", None) or category

        self.write_sep("-", bold=True)
        fill = getattr(self, "_tw").fullwidth - getattr(self, "_width_of_current_line") - 1
        self.write_line(status.upper().rjust(fill), **get_status_color(status))


def enable_terminal_report(config):
    """Enable terminal report."""

    terminalreporter = config.pluginmanager.getplugin("terminalreporter")
    config.pluginmanager.unregister(terminalreporter)
    terminalreporter = ATMTerminalReporter(config)
    config.pluginmanager.register(terminalreporter, "terminalreporter")

    # pretty terminal reporting needs capturing to be turned off ("-s") to function properly
    if getattr(config.option, "pretty", False):
        if getattr(config.option, "capture", None) != "no":
            setattr(config.option, "capture", "no")
            capturemanager = config.pluginmanager.getplugin("capturemanager")
            capturemanager.stop_global_capturing()
            setattr(capturemanager, "_method", getattr(config.option, "capture"))
            capturemanager.start_global_capturing()


def patch_terminal_size(config):
    """Patch terminal size."""

    # this function tries to fix the layout issue related to jenkins console
    terminalreporter = config.pluginmanager.getplugin("terminalreporter")

    if not terminalreporter:
        return

    tw = getattr(terminalreporter, "_tw")

    if not tw:
        return

    try:
        # calculate terminal size from screen dimension (e.g. 1920 -> 192)
        import tkinter
        default_width = min(192, int((tkinter.Tk().winfo_screenwidth() + 9) / 10))
        default_height = int((tkinter.Tk().winfo_screenheight() + 19) / 20)
    except Exception:  # pylint: disable=broad-except
        # tradeoff
        default_width = 152
        default_height = 24

    import shutil
    width, _ = shutil.get_terminal_size((default_width, default_height))
    tw.fullwidth = width


def get_code_base_url():
    """Get current code base url."""

    import subprocess

    try:
        code_base = subprocess.check_output("git config --get remote.origin.url".split()).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        return None

    return code_base


def import_module(module_name):
    """Import and return module if existing."""

    try:
        return pytest.importorskip(module_name)
    except pytest.skip.Exception:
        return None


def intersection(list_a, list_b):
    """Return the intersection of two lists (maintaining the item order of the first list)."""
    result = []
    for item in list_a:
        if (item in list_b) and (item not in result):
            result.append(item)
    return result


def calc_test_result_status(step_results):
    """Calculate overall test result status from list of step results.

        According to Adaptavist test management:

            Blocked & Not Executed -> Blocked
            Blocked & In Progress -> Blocked
            Blocked & Pass -> Blocked
            Blocked & Fail -> Fail

            Fail & Not Executed -> Fail
            Fail & In Progress -> Fail
            Fail & Pass -> Fail

            Pass & Not Executed -> In Progress
            Pass & In Progress -> In Progress

            In Progress & Not Executed -> In Progress
    """
    # map representing status as binary/hex number to be used with & operator
    status_map = {
        "Not Executed": 0xB,  # 1011
        "Pass": 0x7,          # 0111
        "In Progress": 0x3,   # 0011
        "Blocked": 0x1,       # 0001
        "Fail": 0x0           # 0000
    }
    if not step_results:
        return "Not Executed"
    status = 0xF
    for result in step_results:
        status = status & status_map[result["status"]]

    return [k for k, v in status_map.items() if v == status][0]


def get_item_nodeid(item):
    """Build item node id."""
    # note: pytest's item.nodeid could be modified by third party, so build a local one here
    if item.location and len(item.location) > 2:
        return item.location[0].replace("\\", "/") + "::" + item.location[2].replace(".", "::")
    return item.fspath.relto(item.config.rootdir).replace("\\", "/") + "::" + item.getmodpath().replace(".", "::")


def get_item_name_and_spec(nodeid):
    """Split item nodeid into function name and - if existing - callspec res. parameterization."""
    tokens = nodeid.split("[", 1)
    return tokens[0].strip(), "[" + tokens[1].strip() if len(tokens) > 1 else None


def get_status_color(status):
    """Return (markup) color for test result status."""
    colormap = {"passed": {"green": True, "bold": True},
                "failed": {"red": True, "bold": True},
                "blocked": {"blue": True, "bold": True},
                "skipped": {"yellow": True, "bold": True}}

    return colormap.get(status, {})


def get_marker(item, name):
    """Get item marker (wrapper for supporting older and newer pytest versions)."""
    return (getattr(item, "get_closest_marker", None) or getattr(item, "get_marker", None))(name)


def setup_item_collection(items, collected_project_keys, collected_items):
    """Setup and prepare collection of available test methods."""

    # define the test case keys to be processed
    test_case_keys = pytest.test_case_keys

    if pytest.test_run_key:
        test_run = pytest.adaptavist.get_test_run(pytest.test_run_key)
        test_cases = [item["testCaseKey"] for item in test_run.get("items", [])]

        # if test case keys are specified as well, take the intersection of both (if empty then all methods are skipped)
        test_case_keys = intersection(pytest.test_case_keys, test_cases) or [None] if pytest.test_case_keys else test_cases

    # run over all found test methods and collect the relevants
    for item in items:
        item.fullname = get_item_nodeid(item)
        # initialize item's status info
        pytest.item_status_info[item.fullname] = {}
        # initialize item's test result data (see meta_data function down below)
        pytest.test_result_data[item.fullname] = {"comment": None, "attachment": None}

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
                    project_key = pytest.project_key or "TEST"

            if project_key not in collected_project_keys:
                collected_project_keys.append(project_key)

            # initialize refresh info
            _, specs = get_item_name_and_spec(get_item_nodeid(item))
            pytest.test_refresh_info[project_key + "-" + test_case_key + (specs or "")] = None

            # mark this item with appropriate info (easier to read from when creating test results)
            item.add_marker(pytest.mark.testcase(project_key=project_key,
                                                 test_case_key=project_key + "-" + test_case_key,
                                                 test_step_key=test_step_key))

            if test_case_keys:
                # only add specified test cases (to be included in the report)
                if (project_key + "-" + test_case_key) not in test_case_keys:
                    item.add_marker(pytest.mark.skip(reason="skipped as requested"))
                else:
                    collected_items.setdefault(project_key + "-" + test_case_key, []).append(item)
            else:
                # if no specific test cases are given add any test case found (to be included in the report)
                collected_items.setdefault(project_key + "-" + test_case_key, []).append(item)
        elif pytest.skip_ntc_methods:
            # skip methods that are no test case methods
            item.add_marker(pytest.mark.skip)


def apply_test_case_range(collected_items, test_case_range):
    """Apply test case range(s) by skipping excluded test cases."""

    if not collected_items or not test_case_range:
        return collected_items

    len_of_range = len(test_case_range)
    out_of_range = len_of_range > 0
    i = 0
    for key in list(collected_items):
        if i < len_of_range and key == test_case_range[i]:
            out_of_range = False

        if out_of_range:
            for item in collected_items[key]:
                if not next(item.iter_markers(name="skip"), None):
                    item.add_marker(pytest.mark.skip(reason="skipped as requested"))
            collected_items.pop(key)

        if i + 1 < len_of_range and key == test_case_range[i + 1]:
            out_of_range = True
            i += 2

    return collected_items


def create_item_collection(items, collected_project_keys, collected_items):
    """Create the list of test methods to be executed and included in adaptavist report."""

    if pytest.adaptavist and (pytest.project_key or pytest.test_run_key):
        if pytest.test_case_keys:
            # add any specified test cases, even if they are not implemented
            collected_items.update({key: [] for key in pytest.test_case_keys if key not in collected_items})

        # build and order the list of items to be executed and included in adaptavist report
        if not pytest.test_run_key:
            # only include those test cases that are part of collected projects (including test database)
            search_mask = "projectKey IN (\"{0}\")".format("\", \"".join(collected_project_keys + ["TEST"]))
            test_cases = [test_case["key"] for test_case in pytest.adaptavist.get_test_cases(search_mask=search_mask)] if items and getattr(items[0].config.option, "adaptavist") else collected_items.keys()
        else:
            # only include those test cases that are part of this test run
            test_run = pytest.adaptavist.get_test_run(pytest.test_run_key)
            test_cases = [item["testCaseKey"] for item in test_run.get("items", [])]

        # define the execution order for all test cases (specified first, followed by the rest)
        if not pytest.test_case_order:
            pytest.test_case_order = test_cases if pytest.test_run_key else pytest.test_case_keys

        # order items and test cases
        ordered_collected_items = collected_items
        if pytest.test_case_order or pytest.test_case_range:
            ordered_collected_items = {key: collected_items[key] for key in pytest.test_case_order if key in collected_items}
            ordered_collected_items.update({key: collected_items[key] for key in collected_items if key not in ordered_collected_items})
            ordered_collected_items = apply_test_case_range(ordered_collected_items, pytest.test_case_range)
            ordered_items = [item for sublist in ordered_collected_items.values() for item in sublist]
            ordered_items.extend([item for item in items if item not in ordered_items])
            items[:] = ordered_items

        # define the list of test cases to be included in adaptavist report
        # (intersection of collected pytest cases and existing test cases)
        pytest.test_case_keys = intersection(ordered_collected_items.keys(), test_cases)

    pytest.items = items  # for later usage


def setup_report(worker_input):
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

    if pytest.project_key and pytest.test_case_keys:
        if not pytest.test_plan_key and pytest.test_plan_suffix:
            test_plan_name = "{0} {1}".format(pytest.project_key, pytest.test_plan_suffix)
            test_plans = pytest.adaptavist.get_test_plans("projectKey = \"{0}\"".format(pytest.project_key))

            pytest.test_plan_key = ([test_plan["key"] for test_plan in test_plans if test_plan["name"] == test_plan_name] or [test_plan["key"] for test_plan in test_plans if test_plan["name"].endswith(pytest.test_plan_suffix)] or [None])[0]

            if not pytest.test_plan_key:
                pytest.test_plan_key = pytest.adaptavist.create_test_plan(project_key=pytest.project_key, test_plan_name=test_plan_name, folder=pytest.test_plan_folder)

        if not pytest.test_run_key:
            test_plan_name = pytest.adaptavist.get_test_plan(test_plan_key=pytest.test_plan_key).get("name", None) if pytest.test_plan_key else None
            test_run_name = "{0} {1}".format(test_plan_name or pytest.project_key, pytest.test_run_suffix)

            # create new test run either in master (normal sequential mode) or worker0 (load balanced mode) only or - if requested - in each worker
            distribution = worker_input.get("options", {}).get("dist", None)
            if not worker_input or (worker_input.get("workerid", "gw0") in [None, "gw0"]) or (distribution == "each"):
                pytest.test_run_key = pytest.adaptavist.get_test_run_by_name(test_run_name).get("key", None) if (distribution != "each") else None
                test_run_name += f" {worker_input.get('workerid', 'gw0').split('gw')[1]}" if (distribution == "each" and (not pytest.test_environment or pytest.test_environment not in test_run_name)) else ""

                if not pytest.test_run_key:
                    pytest.test_run_key = pytest.adaptavist.create_test_run(project_key=pytest.project_key,
                                                                            test_plan_key=pytest.test_plan_key,
                                                                            test_run_name=test_run_name,
                                                                            test_cases=pytest.test_case_keys,
                                                                            folder=pytest.test_run_folder)

                    pytest.test_refresh_info[pytest.test_run_key] = pytest.test_plan_key

                    # mark test case key to be able to decide whether to use existing test result or to create a new one
                    for test_case_key in pytest.test_case_keys or []:
                        # only mark the first one (e.g. in case of parametrized or repeated methods)
                        key = next((key for key in pytest.test_refresh_info if re.search(test_case_key + r"[ \[\b]", key)), test_case_key)
                        pytest.test_refresh_info[key] = pytest.test_run_key

            elif worker_input and (worker_input.get("workerid", "gw0") not in [None, "gw0"]):
                import time

                # let other workers (if any) wait until test run is available
                found = {}
                while not found:
                    time.sleep(1)
                    found = pytest.adaptavist.get_test_run_by_name(test_run_name)

                pytest.test_run_key = found.get("key", None)

        # connect test plan and test run if not yet done
        if pytest.test_plan_key and pytest.test_refresh_info.get(pytest.test_run_key, None) != pytest.test_plan_key:
            pytest.adaptavist.edit_test_plan(test_plan_key=pytest.test_plan_key, test_runs=[pytest.test_run_key])

            pytest.test_refresh_info[pytest.test_run_key] = pytest.test_plan_key

    # create new environment key if needed
    if pytest.test_case_keys and pytest.test_environment:
        project_key = pytest.adaptavist.get_test_run(pytest.test_run_key).get("projectKey", None) if pytest.test_run_key else pytest.project_key
        # if getpass.getuser().lower() != "jenkins" and not pytest.test_environment.endswith("(local system)"):
        #     pytest.test_environment = pytest.test_environment.strip() + " (local system)"
        if pytest.test_environment not in [environment["name"] for environment in pytest.adaptavist.get_environments(project_key)]:
            pytest.adaptavist.create_environment(project_key, pytest.test_environment)


def create_report(test_case_key, test_step_key, execute_time, skip_status, passed, test_result_data, specs=None):
    """Generate adaptavist test results for given item.

        :param test_case_key: The test case to report.
        :param test_step_key: The test step to report.
        :param execute_time: The time spent for execution.
        :param skip_status: pytest marker, may hold either a pytest.mark.skip or pytest.mark.block
        :param passed: True or False, depending on test result.
        :param test_result_data: additional data containing comments, attachments, etc.
    """
    adaptavist = pytest.adaptavist

    test_run_key = pytest.test_run_key

    if test_run_key and test_case_key in (pytest.test_case_keys or []):

        test_result = adaptavist.get_test_result(test_run_key, test_case_key)

        if not test_result or pytest.test_refresh_info[test_case_key + (specs or "")] != test_run_key:
            # create new test result to prevent accumulation of data
            # when using an existing test run key multiple times
            adaptavist.create_test_result(test_run_key=test_run_key,
                                          test_case_key=test_case_key,
                                          environment=pytest.test_environment,
                                          status=None)

            # refetch result
            test_result = adaptavist.get_test_result(test_run_key, test_case_key)

            pytest.test_refresh_info[test_case_key + (specs or "")] = test_run_key

        # touch parametrized/repeated items
        for key in pytest.test_refresh_info:
            if re.search(test_case_key + r"[ \[\b]", key):
                pytest.test_refresh_info[key] = pytest.test_run_key

        # get optional meta data (comments, attachments) of test case method
        comment = skip_status.kwargs.get("reason", None) if skip_status else test_result_data.get("comment", None)
        description = None if skip_status else test_result_data.get("description", None)
        attachment = None if skip_status else test_result_data.get("attachment", None)

        header = "---------------------------------------- " + datetime.now().strftime("%Y%m%d%H%M") + " ----------------------------------------" if specs else ""

        if not skip_status and not test_step_key:
            # update test case with CI related info
            adaptavist.edit_test_case(test_case_key,
                                      labels=["automated"],
                                      build_urls=[pytest.build_url if not pytest.build_url else f"<a href=\"{pytest.build_url}\">{pytest.build_url}</a>"],
                                      code_bases=[pytest.code_base if not pytest.code_base else f"<a href=\"{pytest.code_base}\">{pytest.code_base}</a>"])

        if test_step_key:

            # in case of parameterization or repetition the status will be Fail if one iteration failed
            last_result = next((result for result in test_result.get("scriptResults", []) if result["index"] == int(test_step_key) - 1), {})

            if skip_status and last_result.get("status", None) != "Fail":
                status = "Blocked" if skip_status.name == "block" else "Not Executed"
            else:
                status = "Pass" if passed and last_result.get("status", None) != "Fail" else "Fail"

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + ((description + "<br>") if description else "") + (last_result.get("comment", "") if specs else "")

            result_id = adaptavist.edit_test_script_status(test_run_key=test_run_key,
                                                           test_case_key=test_case_key,
                                                           step=int(test_step_key),
                                                           environment=pytest.test_environment,
                                                           status=status,
                                                           comment=comments if (specs or last_result.get("status", None) != "Fail") else None)

            if attachment:
                adaptavist.add_test_script_attachment(test_result_id=result_id,
                                                      step=int(test_step_key),
                                                      attachment=attachment,
                                                      filename=test_result_data.get("filename", None))

            # adjust parent test result status according to current test script results
            test_result = adaptavist.get_test_result(test_run_key, test_case_key)
            status = calc_test_result_status(test_result.get("scriptResults", []))

            comments = None
            if skip_status:
                # modify comment to add info about blocked or skipped script steps
                comments = ("step {0} {1}:".format(test_step_key, "blocked" if skip_status.name == "block" else "skipped") + (("<br>" + comment + "<br>") if comment else ""))
            elif not passed:
                # modify comment to add info about failure in script steps
                comments = ("step {0} failed:".format(test_step_key) + (("<br>" + comment + "<br>") if comment else ""))

            # find the right position to insert comments of this test execution (in case of parametrized or repeated test methods)
            index = test_result.get("comment", "").find("---------------------------------------- ")

            adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                               test_case_key=test_case_key,
                                               environment=pytest.test_environment,
                                               status=status,
                                               comment=(test_result.get("comment", "") + (comments or "")) if index < 0 else (test_result.get("comment", "")[:index] + (comments or "") + test_result.get("comment", "")[index:]),
                                               execute_time=execute_time)

        else:
            # change parent test result status only if blocked or failed or if there was no previous failure
            # if test_result.get("status", "Not Executed") == "Blocked" and skip_status:
            #    # no need to proceed here, info about blocked steps is enough
            #    return
            status = test_result.get("status", "Not Executed")
            if status == "Not Executed" and skip_status:
                status = "Blocked" if skip_status.name == "block" else "Not Executed"
            elif status == "Fail" or (not passed and not skip_status):
                status = "Fail"
            elif status == "Not Executed" and not skip_status:
                status = "Pass" if passed else "Fail"

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + ((description + "<br>") if description else "") + test_result.get("comment", "")

            result_id = adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                                           test_case_key=test_case_key,
                                                           environment=pytest.test_environment,
                                                           status=status,
                                                           comment=comments,
                                                           execute_time=execute_time)

            if attachment:
                adaptavist.add_test_result_attachment(test_result_id=result_id,
                                                      attachment=attachment,
                                                      filename=test_result_data.get("filename", None))


def html_row(condition, message):
    """Generate an html status row to be displayed in test case results."""
    return f"<div style='padding: 2pt'><span style='width: auto; margin-right: 4pt; padding: 2pt; border-radius: 4px; background-color: {'rgb(58, 187, 75)' if condition else 'rgb(223, 47, 54)'}; color: white; font-family: monospace; font-size: 10pt; font-weight: bold;'>{'PASS' if condition else 'FAIL'}</span>{message}</div>" if message else None


def is_unexpected_exception(exc_type):
    """Check if exception type is unexpected (any exception except AssertionError, pytest.block.Exception, pytest.skip.Exception)."""

    if exc_type and (isinstance(exc_type, (Exception, BaseException)) or issubclass(exc_type, (Exception, BaseException))):
        # the following lines are necessary to support 2.x versions of pytest-assume which raise FailedAssumption exceptions on failed assumptions
        pytest_assume = import_module("pytest_assume")
        FailedAssumption = pytest_assume.plugin.FailedAssumption if pytest_assume and hasattr(pytest_assume, "plugin") and hasattr(pytest_assume.plugin, "FailedAssumption") else None
        return exc_type not in (None, FailedAssumption, AssertionError, pytest.skip.Exception)
    return False


def build_exception_info(item_name, exc_type, exc_value, traceback):
    """Generate description info about exceptions."""

    exc_info = None

    if exc_type and (exc_type, exc_value, traceback) != pytest.item_status_info[item_name].get("exc_info", None):
        if exc_type is AssertionError:
            # in case of assertion only report exception value (not line of code)
            exc_info = str(exc_value).partition("\n")[0]
        elif exc_type is pytest.skip.Exception:
            exc_info = str(exc_value).partition("\n")[0]
        else:
            exc_dict = {"path": os.path.relpath(traceback.tb_frame.f_code.co_filename), "line": traceback.tb_lineno, "info": str(exc_value).partition("\n")[0]}
            exc_info = exc_dict["info"] + " (" + exc_dict["path"] + ", line " + str(exc_dict["line"]) + ")"

        # avoid reporting this exception a second time
        pytest.item_status_info[item_name]["exc_info"] = (exc_type, exc_value, traceback)

    return exc_info


def build_report_description(item, call, report, skip_status):
    """Generate standard test results for given item.

        :param item: The item to report.
        :param call: The call info object.
        :param report: The report object.
        :param skip_status: pytest marker, may hold either a pytest.mark.skip or pytest.mark.block
    """
    report.description = (skip_status.kwargs.get("reason", None) if skip_status else "") or pytest.test_result_data[item.fullname].get("comment", None) or ""

    if call.when != "teardown" or call.excinfo:
        test_case_key = None
        test_case_name = None
        priority = None
        marker = get_marker(item, "testcase")
        if marker is not None:
            test_case_key = marker.kwargs["test_case_key"]
            if test_case_key in (pytest.test_case_keys or []):
                test_case_info = pytest.adaptavist.get_test_case(test_case_key)
                test_case_name = test_case_info.get("name", None)
                priority = test_case_info.get("priority", None)

        if not (call.excinfo and call.excinfo.type is pytest.skip.Exception) and not skip_status:
            # append info from test case steps (if existing)
            if test_case_key:
                subkeys = [key for key in pytest.test_result_data if key != item.fullname and key.startswith(item.fullname)]
                for key in subkeys:
                    report.description = "<br>".join((report.description, f"{key}{' blocked' if pytest.test_result_data[key].get('blocked', None) is True else ''}:".format(key), pytest.test_result_data[key].get("comment", None) or ""))

        key = get_item_nodeid(item)

        outcome = report.outcome if not skip_status else ("blocked" if skip_status.name == "block" else "skipped")

        pytest.report[key] = {"test_case_key": test_case_key, "test_case_name": test_case_name, "priority": priority, "status": outcome, "duration": report.duration, "details": report.description or "",
                              "exc_info": is_unexpected_exception(pytest.item_status_info[item.fullname].get("exc_info", (None, None, None))[0])}


def build_terminal_report(when, item, status=None, step=None, level=1):
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

    if hasattr(pytest, "reporter") and getattr(item.config.option, "pretty", False):
        if when == "setup":
            if not step:
                title, specs = get_item_name_and_spec(get_item_nodeid(item) or "")
                pytest.reporter.line("")
                pytest.reporter.write_sep("-", title, bold=True)
                pytest.reporter.write_line(inspect.cleandoc(item.obj.__doc__ or ""))
                pytest.reporter.write_line("parameterization " + specs if specs else "")
            if step and item.config.option.verbose > 1:
                pytest.reporter.write_sep("-", "Step " + str(step), bold=True)
                pytest.reporter.write(doc_string + ("\n" if doc_string else ""))
        elif when == "call":
            if not step:
                pytest.reporter.write_sep("-", bold=True)
                fill = getattr(pytest.reporter, "_tw").fullwidth - getattr(pytest.reporter, "_width_of_current_line") - 1
                pytest.reporter.write_line(status.upper().rjust(fill), **get_status_color(status))
            if step and item.config.option.verbose > 1:
                fill = getattr(pytest.reporter, "_tw").fullwidth - getattr(pytest.reporter, "_width_of_current_line") - 1
                pytest.reporter.write_line(status.upper().rjust(fill), **get_status_color(status))
    elif hasattr(pytest, "reporter"):
        if when == "setup":
            if step and item.config.option.verbose > 1:
                pytest.reporter.line("")
        if when == "call":
            if step and item.config.option.verbose > 1:
                pytest.reporter.line(get_item_nodeid(item) + " step " + str(step) + " " + status.upper())


def assume(expr, msg=None, level=1):
    """Assume expression.

        :param expr: The expression or condition to be checked.
        :param msg: The message in the case of failure.
        :param level: The stack trace level (1 = the caller's level, 2 = the caller's caller level, 3 = ...).
    """
    if not expr:
        entry = None
        exc_tb = None
        pretty_locals = None

        (frame, filename, line, _, contextlist) = inspect.stack()[max(1, level)][0:5]
        # get filename, line, and context
        path = os.path.relpath(filename)
        context = msg or contextlist[0].lstrip()
        if path and line and context:
            entry = u"{path}:{line}: AssumptionFailure\n\t{context}".format(**locals())

        if getattr(pytest, "_showlocals", False):
            try:
                from py.io import saferepr
            except ImportError:
                saferepr = repr

            # Debatable whether we should display locals for
            # every failed assertion, or just the final one.
            # I'm defaulting to per-assumption, just because vars
            # can easily change between assumptions.
            pretty_locals = ["%-10s = %s" % (name, saferepr(val)) for name, val in frame.f_locals.items()]
            getattr(pytest, "_assumption_locals", []).append(pretty_locals)

        # the following lines are necessary to support both 1.x and 2.x versions of pytest-assume
        pytest_assume = import_module("pytest_assume")
        if pytest_assume and hasattr(pytest_assume, "plugin") and hasattr(pytest_assume.plugin, "Assumption"):
            # 2.x
            getattr(pytest, "_failed_assumptions", []).append(pytest_assume.plugin.Assumption(entry, exc_tb, pretty_locals))
        else:
            # 1.x
            getattr(pytest, "_failed_assumptions", []).append(entry)


def handle_failed_assumptions(item, call, report):
    """Handle failed assumptions (simulating pytest-assume, if not available)."""

    if hasattr(pytest, "assume") and pytest.assume != assume:
        # use 3rd party handling
        return

    if call.when == "call" and getattr(pytest, "_failed_assumptions", []):
        evalxfail = getattr(item, '_evalxfail', None)
        if evalxfail and evalxfail.wasvalid() and evalxfail.istrue():
            report.outcome = "skipped"
            report.wasxfail = evalxfail.getexplanation()
        else:
            summary = 'Failed Assumptions: %s' % len(getattr(pytest, "_failed_assumptions", []))
            if report.longrepr:
                # Do we want to have the locals displayed here as well?
                # I'd say no, because the longrepr would already be displaying locals.
                report.sections.append((summary, "".join(getattr(pytest, "_failed_assumptions", []))))
            else:
                if getattr(pytest, "_assumption_locals", []):
                    assume_data = zip(getattr(pytest, "_failed_assumptions", []), getattr(pytest, "_assumption_locals", []))
                    longrepr = ["{0}\n{1}\n\n".format(assumption, "\n".join(flocals)) for assumption, flocals in assume_data]
                else:
                    longrepr = ["\n\n".join(getattr(pytest, "_failed_assumptions", []))]

                longrepr.append("-" * 60)
                longrepr.append(summary)
                report.longrepr = '\n'.join(longrepr)

            report.outcome = "failed"

    # deleting the existing list and all its references
    del getattr(pytest, "_failed_assumptions", [])[:]
    del getattr(pytest, "_assumption_locals", [])[:]


def get_executor():
    """Get executor name."""

    build_url = os.environ.get("BUILD_URL", None)
    jenkins_url = os.environ.get("JENKINS_URL", None)
    is_jenkins = build_url and jenkins_url and build_url.startswith(jenkins_url)
    return "jenkins" if is_jenkins else getpass.getuser().lower()


def atm_user_is_valid(user):
    """Check if user is known to Adaptavist/Jira."""

    cfg = ATMConfiguration()

    return user in Adaptavist(cfg.get("jira_server", ""), cfg.get("jira_username", ""), cfg.get("jira_password", "")).get_users()


def atm_configure(config):
    """Setup adaptavist reporting based on given requirements (config)."""

    cfg = ATMConfiguration()

    if not getattr(pytest, "adaptavist", None):
        pytest.adaptavist = Adaptavist(cfg.get("jira_server", ""), cfg.get("jira_username", ""), cfg.get("jira_password", ""))
    if not getattr(pytest, "project_key", None):
        pytest.project_key = cfg.get("project_key", None)

    # support of multiple environments
    # in case of using xdist's "each" mode, a test run for each specified environment is created
    # and test_environment can be used (when given as a list or comma-separated string) to specify keys for each test run resp. worker node
    worker_input = getattr(config, "workerinput", {})
    distribution = worker_input.get("options", {}).get("dist", None)
    index = int(worker_input.get("workerid", "gw0").split("gw")[1]) if (distribution == "each") else 0

    entry = getattr(pytest, "test_environment", []) or cfg.get("test_environment", []) or []
    test_environments = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry
    pytest.test_environment = test_environments[index if index < len(test_environments) else -1] if test_environments else None

    entry = getattr(pytest, "test_case_keys", []) or cfg.get("test_case_keys", []) or []
    pytest.test_case_keys = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    entry = getattr(pytest, "test_case_order", []) or cfg.get("test_case_order", []) or []
    pytest.test_case_order = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    entry = getattr(pytest, "test_case_range", []) or cfg.get("test_case_range", []) or []
    pytest.test_case_range = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    if not getattr(pytest, "test_plan_key", None):
        pytest.test_plan_key = cfg.get("test_plan_key", None)
    if not getattr(pytest, "test_plan_folder", None):
        pytest.test_plan_folder = cfg.get("test_plan_folder", None)
    if not getattr(pytest, "test_plan_suffix", None):
        pytest.test_plan_suffix = cfg.get("test_plan_suffix", None)
    if not getattr(pytest, "test_run_key", None):
        pytest.test_run_key = cfg.get("test_run_key", None)
    if not getattr(pytest, "test_run_folder", None):
        pytest.test_run_folder = cfg.get("test_run_folder", None)
    if not getattr(pytest, "test_run_suffix", None):
        pytest.test_run_suffix = cfg.get("test_run_suffix", "test run " + datetime.now().strftime("%Y%m%d%H%M"))
    if getattr(pytest, "skip_ntc_methods", None) is None:
        pytest.skip_ntc_methods = cfg.get_bool("skip_ntc_methods", False)

    return True


class Blocked(pytest.skip.Exception):  # pylint: disable=too-few-public-methods
    """Block exception used to abort test execution and set result status to "Blocked"."""


def pytest_addoption(parser):
    """Add options to control plugin."""

    group = parser.getgroup("adaptavist", "adaptavist test reporting")
    group.addoption("--adaptavist", action="store_true", default=False,
                    help="Enable adaptavist reporting (default: False)")

    group.addoption("--pretty", action="store_true", dest="pretty", default=False,
                    help="Make pytest terminal output more readable (default: False)")


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Prepare and start logging/reporting (called at the beginning of the test process)."""

    # register custom markers
    config.addinivalue_line("markers", "testcase: mark test method as test case implementation (for internal use only)")
    config.addinivalue_line("markers", "project(project_key): mark test method to be related to given project (used to create appropriate test case key")
    config.addinivalue_line("markers", "block(reason): mark test method to be blocked")

    if config.getoption("-h") or config.getoption("--help"):
        return

    # support for pytest-assume >= 1.2.1 (needs to be done after any potential call of pytest_configure)
    if hasattr(pytest, "assume") and not hasattr(pytest, "_failed_assumptions"):
        pytest_assume = import_module("pytest_assume")
        if pytest_assume and hasattr(pytest_assume, "plugin"):
            # pytest-assume 1.2.1 is using _FAILED_ASSUMPTIONS and _ASSUMPTION_LOCALS
            setattr(pytest, "_failed_assumptions", getattr(pytest_assume.plugin, "_FAILED_ASSUMPTIONS", []))
            setattr(pytest, "_assumption_locals", getattr(pytest_assume.plugin, "_ASSUMPTION_LOCALS", []))

    if not hasattr(pytest, "_failed_assumptions"):
        # overwrite all assumption related attributes by local ones
        setattr(pytest, "_failed_assumptions", [])
        setattr(pytest, "_assumption_locals", [])
        pytest.assume = assume

    setattr(pytest, "_showlocals", config.getoption("showlocals"))

    # support for pytest.block
    def block(msg=""):
        __tracebackhide__ = True
        raise Blocked(msg=msg)

    block.Exception = Blocked

    pytest.block = block

    # Store metadata for later usage (e.g. adaptavist traceability).
    metadata = getattr(config, "_metadata", {}) or os.environ

    build_usr = get_executor()
    build_url = metadata.get("BUILD_URL", None)
    jenkins_url = metadata.get("JENKINS_URL", None)
    code_base = metadata.get("GIT_URL", None) or get_code_base_url()
    branch = metadata.get("GIT_BRANCH", None)
    commit = metadata.get("GIT_COMMIT", None)

    pytest.build_url = "/".join(build_url.split("/")[:5]) if build_url and jenkins_url and build_url.startswith(jenkins_url) else build_url
    pytest.code_base = code_base.replace(":", "/").replace(".git", "").replace("git@", "https://") if code_base and code_base.startswith("git@") else code_base

    # only report results to adaptavist if:
    #     - branch is master
    #     - user is jenkins
    #     - env is jenkins
    # note: we might need the possibility to create adaptavist results from a local test run (beit for testing purpose or whatever)

    # if user is jenkins
    #   if branch is master then report using getpass.getuser()
    #   else disable report
    # else
    #   report using getpass.getuser()

    # => automated flag set and executedby = "jenkins" means official test run
    # => automated flag set and executedby != "jenkins" means inofficial test run (not valid with respect to DoD)
    if build_usr == "jenkins" and build_url and jenkins_url and build_url.startswith(jenkins_url):
        if branch != "origin/master":
            # disable reporting
            setattr(config.option, "adaptavist", False)

    if build_usr != "jenkins":
        if not atm_user_is_valid(build_usr):
            # disable reporting
            setattr(config.option, "adaptavist", False)

    # init the terminal reporter
    if not hasattr(config, "workerinput"):
        enable_terminal_report(config)

    patch_terminal_size(config)

    pytest.reporter = config.pluginmanager.getplugin("terminalreporter")

    if pytest.reporter:
        pytest.reporter.section("ATM build meta data", bold=True)

        pytest.reporter.line("build_usr: %s" % (build_usr or "unknown"))
        pytest.reporter.line("build_url: %s" % (build_url or "unknown"))
        pytest.reporter.line("code_base: %s %s %s" % (code_base or "unknown", (branch or "unknown") if code_base else "", (commit or "unknown") if code_base and branch else ""))
        pytest.reporter.line("reporting: %s" % ("enabled" if getattr(config.option, "adaptavist", False) else "disabled"))

    logger = logging.getLogger("pytest-adaptavist")
    logger_handler = logging.StreamHandler()
    logger_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(logger_handler)
    logger.propagate = False


if import_module("xdist"):
    @pytest.hookimpl(trylast=True)
    def pytest_configure_node(node):
        """This is called in case of using xdist to pass data to worker nodes."""
        node.workerinput["options"] = {
            "dist": node.config.option.dist,
            "numprocesses": node.config.option.numprocesses
        }


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):  # pylint: disable=unused-argument
    """This is called before test process is exited."""

    if config.getoption("-h") or config.getoption("--help"):
        return

    # create and output Adaptavist test cycle information
    if getattr(config.option, "adaptavist", False) and getattr(pytest, "reporter", None):

        pytest.reporter.section("ATM test cycle info", bold=True)

        pytest.reporter.line("project_key:   %s" % getattr(pytest, "project_key", None))
        pytest.reporter.line("test_plan_key: %s" % getattr(pytest, "test_plan_key", None))
        pytest.reporter.line("test_run_key:  %s" % getattr(pytest, "test_run_key", None))
        if getattr(pytest, "test_run_keys", None) and getattr(pytest, "test_run_keys", [None]) != [getattr(pytest, "test_run_key", None)]:
            pytest.reporter.line("cycle_key(s):  %s" % ", ".join(pytest.test_run_keys))

        traceability = None
        test_summary = None
        score_matrix = None
        base_url = ATMConfiguration().get("jira_server", "")
        if base_url and getattr(pytest, "project_key", None) and getattr(pytest, "test_run_key", None):
            cycle_string = "%22%2C%20%22".join(pytest.test_run_keys) if getattr(pytest, "test_run_keys", None) else pytest.test_run_key or ""
            traceability = f"{base_url}/secure/Tests.jspa#/reports/traceability/report/view?tql=testResult.projectKey%20IN%20%28%22{pytest.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TRACEABILITY_REPORT.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"
            test_summary = f"{base_url}/secure/Tests.jspa#/reports/testresults/board/view?tql=testResult.projectKey%20IN%20%28%22{pytest.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_BOARD.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"
            score_matrix = f"{base_url}/secure/Tests.jspa#/reports/testresults/scorecard/coverage/view?tql=testResult.projectKey%20IN%20%28%22{pytest.project_key}%22%29%20AND%20testRun.key%20IN%20%28%22{cycle_string}%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_SCORECARD_BY_COVERAGE.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS"

        pytest.reporter.line("traceability:  %s" % traceability)
        pytest.reporter.line("test_summary:  %s" % test_summary)
        pytest.reporter.line("score_matrix:  %s" % score_matrix)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """This is called after whole test run has finished."""

    yield

    if hasattr(session.config, "workerinput"):
        return

    # create and output final status line (used by jenkins pipeline)
    exceptions_raised = 0
    high_prios_failed = 0

    report = getattr(pytest, "report", {}) or {}

    not_built = True
    for key in report:
        exceptions_raised += 1 if report[key]["exc_info"] else 0
        high_prios_failed += 1 if report[key]["status"] == "failed" and report[key]["priority"] == "High" else 0
        not_built = not_built and report[key]["status"] not in ["passed", "failed"]

    if exceptions_raised or high_prios_failed or exitstatus in (3, 4):
        status = "FAILURE"
    elif exitstatus == 1:
        status = "UNSTABLE"
    elif exitstatus == 2:
        status = "ABORTED"
    elif exitstatus == 5 or not_built:
        status = "NOT_BUILT"
    else:
        status = "SUCCESS"

    line = f"final_status ({status}): {getattr(pytest, 'project_key', None)}, {getattr(pytest, 'test_plan_key', None)}, {', '.join(getattr(pytest, 'test_run_keys', []) or [str(getattr(pytest, 'test_run_key', None))])}, "
    line += f"{high_prios_failed} high prio tc(s) failed, {exceptions_raised} exception(s) raised, exitstatus={exitstatus}"

    colormap = {"ABORTED": "white",
                "FAILURE": "red",
                "NOT_BUILT": "white",
                "SUCCESS": "green",
                "UNSTABLE": "yellow"}

    markup = {colormap[status]: True, "bold": True}

    if pytest.reporter:
        pytest.reporter.write_sep("=", **markup)
        pytest.reporter.write_line(line, **markup)
        pytest.reporter.write_sep("=", **markup)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):  # pylint: disable=unused-argument
    """Collect items matching given requirements (config)
       and prepare adaptavist reporting.

        The following parameters need to be set before (e.g. either in pytest names or as class member):
        :param pytest.project_key: to create a new test run
        :param pytest.test_run_key: to use existing test run
        :param pytest.test_run_suffix: as option when creating new test run (e.g. to specify release version etc.)
        :param pytest.test_case_keys: as option to run only a subset of implemented test cases
    """
    # dictionary to store temporal info about test items
    pytest.item_status_info = {}
    # dictionary to control whether to create new or to update existing test results
    pytest.test_refresh_info = {}
    # to be able to store data inside of test methods (see meta_data function down below)
    pytest.test_result_data = {}
    # dictionary to store final report
    pytest.report = {}

    for item in items:
        item.fullname = get_item_nodeid(item)
        # initialize item's status info
        pytest.item_status_info[item.fullname] = {}
        # initialize item's test result data (see meta_data function down below)
        pytest.test_result_data[item.fullname] = {"comment": None, "attachment": None}

    # store items for later usage
    pytest.items = items

    if not atm_configure(config):
        return

    collected_project_keys = []
    collected_items = {}

    setup_item_collection(items, collected_project_keys, collected_items)
    create_item_collection(items, collected_project_keys, collected_items)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """This is called before calling the test item (i.e. before any parameter/fixture call).

        Used to skip test items dynamically (e.g. triggered by some other item or control function).
    """
    build_terminal_report(when="setup", item=item)

    skip_status = get_marker(item, "block") or get_marker(item, "skip")

    skip_reason = None

    if not skip_reason and skip_status:
        skip_reason = skip_status.kwargs.get("reason", None)
    if not skip_reason and pytest.test_result_data[item.fullname].get("blocked", None) is True:
        skip_reason = pytest.test_result_data[item.fullname].get("comment", None)

    if skip_reason:
        pytest.skip(msg=skip_reason)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """This is called at setup, run/call and teardown of test items.

        Generates adaptavist test run results from test reports.
    """
    outcome = yield

    report = outcome.get_result()

    report.item_info = {}
    report.item_info["atmcfg"] = {"project_key": pytest.project_key, "test_environment": pytest.test_environment, "test_plan_key": pytest.test_plan_key, "test_run_key": pytest.test_run_key}
    report.item_info["nodeid"] = get_item_nodeid(item)
    report.item_info["docstr"] = inspect.cleandoc(item.obj.__doc__ or "")

    skip_status = get_marker(item, "block") or get_marker(item, "skip")

    if call.when == "setup":
        if getattr(item.config.option, "adaptavist", False):
            # setup report only if adaptavist reporting is enabled
            setup_report(getattr(item.config, "workerinput", {}))
            report.item_info["atmcfg"] = {"project_key": pytest.project_key, "test_plan_key": pytest.test_plan_key, "test_run_key": pytest.test_run_key}

        if not call.excinfo and not skip_status and not pytest.test_result_data[item.fullname].get("blocked", None) is True:
            # no skipped or blocked methods to report
            return
    elif call.when != "call":
        return

    # if method was blocked dynamically (during call) an appropriate marker is used
    # to handle the reporting in the same way as for statically blocked methods
    # (status will be reported as "Blocked" with given comment in Adaptavist)
    if not skip_status and ((call.excinfo and call.excinfo.type in (pytest.block.Exception, pytest.skip.Exception)) or (not call.excinfo and pytest.test_result_data[item.fullname].get("blocked", None) is True)):
        reason = pytest.test_result_data[item.fullname].get("comment", None) or (str(call.excinfo.value).partition("\n")[0] if call.excinfo and call.excinfo.type in (pytest.block.Exception, pytest.skip.Exception) else None)
        skip_status = pytest.mark.block(reason=reason) if ((call.excinfo and call.excinfo.type is pytest.block.Exception) or pytest.test_result_data[item.fullname].get("blocked", None) is True) else pytest.mark.skip(reason=reason)
        if report.outcome != "skipped":
            report.outcome = "skipped"  # to mark this as SKIPPED in pytest reports
            report.longrepr = (__file__, getattr(sys, "_getframe")().f_lineno if hasattr(sys, "_getframe") else None, f"Skipped: {reason or 'blocked dynamically or partially'}")

    # report exceptions
    if call.excinfo:
        exc_info = build_exception_info(item.fullname, call.excinfo.type, call.excinfo.value, getattr(call.excinfo.traceback[-1], "_rawentry"))

        if exc_info and exc_info not in (pytest.test_result_data[item.fullname].get("comment", None) or ""):

            if (call.excinfo.type is not pytest.skip.Exception) and not skip_status:
                pytest.test_result_data[item.fullname]["comment"] = "".join((pytest.test_result_data[item.fullname].get("comment", None) or "", html_row(False, exc_info)))

    # handling failed assumptions
    handle_failed_assumptions(item, call, report)

    build_report_description(item, call, report, skip_status)

    build_terminal_report(when="call", item=item, status=report.outcome if not skip_status else ("blocked" if skip_status.name == "block" else "skipped"))

    report.item_info["report"] = pytest.report[get_item_nodeid(item)]

    if not getattr(item.config.option, "adaptavist", False):
        # adaptavist reporting disabled: no need to proceed here
        return

    if pytest.test_result_data[item.fullname].get("done", False):
        # this item has been reported already within a meta block context (see below)
        return

    marker = get_marker(item, "testcase")
    if marker is not None:

        test_case_key = marker.kwargs["test_case_key"]
        test_step_key = marker.kwargs["test_step_key"]

        _, specs = get_item_name_and_spec(get_item_nodeid(item))
        create_report(test_case_key, test_step_key, call.stop - call.start, skip_status, report.passed, pytest.test_result_data[item.fullname], specs)


@pytest.fixture(scope="function")
def meta_data(request):
    """This can be used to store data inside of test methods."""
    return pytest.test_result_data[request.node.fullname]


@pytest.fixture(scope="function")
def meta_block(request):
    """This can be used to create reports for test blocks/steps immediately during test method call.
        ```
        with meta_block(step):
            # do your thing here
            pytest.assume(...)
        ```
    """
    def get_meta_block(step=None, timeout=META_BLOCK_TIMEOUT):
        """Return a meta block context to process single test blocks/steps."""
        return MetaBlock(request, step, timeout=timeout)

    return get_meta_block


class MetaBlockAborted(Exception):
    """Internal exception used to abort meta block execution."""


class MetaBlock():
    """Context Manager class used for processing/reporting single test blocks/steps."""

    from enum import IntEnum

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

    def __init__(self, request, step=None, timeout=META_BLOCK_TIMEOUT):
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
            build_terminal_report(when="setup", item=self.item, step=self.step, level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)')
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
        if not skip_status and ((exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception)) or (exc_type in (None, MetaBlockAborted) and self.data.get("blocked", None) is True)):
            reason = self.data.get("comment", None) or (str(exc_value).partition("\n")[0] if exc_type and exc_type in (pytest.block.Exception, pytest.skip.Exception) else None)
            skip_status = pytest.mark.block(reason=reason) if ((exc_type and exc_type is pytest.block.Exception) or self.data.get("blocked", None) is True) else pytest.mark.skip(reason=reason)

        # report exceptions
        if exc_type and exc_type is not MetaBlockAborted:
            exc_info = build_exception_info(self.item.fullname, exc_type, exc_value, traceback)

            if exc_info and exc_info not in (self.data.get("comment", None) or ""):
                if (exc_type is not pytest.skip.Exception) and not skip_status:
                    self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row(False, exc_info)))

        passed = not exc_type and (len(getattr(pytest, "_failed_assumptions", [])) <= len(self.failed_assumptions))
        status = ("passed" if passed else "failed") if not skip_status else ("blocked" if (skip_status.name == "block" or self.data.get("blocked", None)) else "skipped")

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid", None) if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist", None) == "each" else None
        getattr(self.item, "meta_block_cb", lambda **kwargs : None)(signature="_".join(filter(None, (prefix, self.item.name, str(self.step) if self.step else "x"))), status=status)

        if self.step:
            build_terminal_report(when="call", item=self.item, status=status, step=self.step, level=2)  # level = 2 to get info from outside of this plugin (i.e. caller of 'with metablock(...)'))

        # adjust parent's test result status if necessary (needed for makereport call later)
        if pytest.test_result_data[self.item.fullname].get("blocked", None) is True:
            if not passed and not skip_status:
                pytest.test_result_data[self.item.fullname]["blocked"] = None
        else:
            if self.data.get("blocked", None) is True:
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

        attachment = kwargs.pop("attachment", None)
        filename = kwargs.pop("filename", None)
        description = kwargs.pop("description", None)
        message_on_fail = kwargs.pop("message_on_fail", None) or message
        message_on_pass = kwargs.pop("message_on_pass", None)

        assert not kwargs, "Unknown arguments: %r" % kwargs

        if attachment:
            self.data["attachment"] = attachment
            self.data["filename"] = filename

        if not condition and message_on_fail:
            self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row(condition, message_on_fail)))
        elif condition and message_on_pass:
            self.data["comment"] = "".join((self.data.get("comment", None) or "", html_row(condition, message_on_pass)))

        if description:
            self.data["description"] = "<br>".join((self.data.get("description", None) or "", description))

        # custom item callback
        prefix = getattr(self.item.config, "workerinput", {}).get("workerid", None) if getattr(self.item.config, "workerinput", {}).get("options", {}).get("dist", None) == "each" else None
        self.__dict__["numchecks"] = self.__dict__.get("numchecks", 0) + 1
        getattr(self.item, "meta_block_condition_cb", lambda **kwargs : None)(
            signature="_".join(filter(None, (prefix, self.item.name, str(self.step) if self.step else "x", str(self.__dict__["numchecks"])))),
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
