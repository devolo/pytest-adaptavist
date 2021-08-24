import inspect
import os
import re
from datetime import datetime

import pytest


def assume(expr, msg=None, level=1):
    """Assume expression.

        :param expr: The expression or condition to be checked.
        :param msg: The message in the case of failure.
        :param level: The stack trace level (1 = the caller's level, 2 = the caller's caller level, 3 = ...).
    """
    if expr:
        return

    entry = None
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
        exc_tb = None
        # 2.x
        getattr(pytest, "_failed_assumptions", []).append(pytest_assume.plugin.Assumption(entry, exc_tb, pretty_locals))
    else:
        # 1.x
        getattr(pytest, "_failed_assumptions", []).append(entry)


def build_exception_info(item_name, exc_type, exc_value, traceback):
    """Generate description info about exceptions."""

    exc_info = None

    if exc_type and (exc_type, exc_value, traceback) != pytest.item_status_info[item_name].get("exc_info", None):
        if exc_type is AssertionError or exc_type is pytest.skip.Exception:
            # in case of assertion only report exception value (not line of code)
            exc_info = str(exc_value).partition("\n")[0]
        else:
            exc_dict = {"path": os.path.relpath(traceback.tb_frame.f_code.co_filename), "line": traceback.tb_lineno, "info": str(exc_value).partition("\n")[0]}
            exc_info = f'{exc_dict["info"]} ({exc_dict["path"]}, line {exc_dict["line"]} )'

        # avoid reporting this exception a second time
        pytest.item_status_info[item_name]["exc_info"] = (exc_type, exc_value, traceback)

    return exc_info


def build_terminal_report(when, item, status=None, step=None, level=1):
    """Generate (pretty) terminal output.

        :param when: The call info ("setup", "call").
        :param item: The item to report.
        :param status: The status ("passed", "failed", "skipped", "blocked").
        :param item: The step index to report.
        :param level: The stack trace level (1 = the caller's level, 2 = the caller's caller level, 3 = ...).
    """

    if not hasattr(pytest, "reporter"):
        return

    # extract doc string from source
    (frame, _, line, _, _) = inspect.stack()[level][0:5]
    source_list = inspect.getsourcelines(frame)
    source_code = "".join(source_list[0][line - source_list[1]:])
    docs = re.findall(r"^[\s]*\"\"\"(.*?)\"\"\"", source_code, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    doc_string = inspect.cleandoc(docs[0]) if docs else ""

    if getattr(item.config.option, "pretty", False):
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
    else:
        if when == "setup" and step and item.config.option.verbose > 1:
            pytest.reporter.line("")
        if when == "call" and step and item.config.option.verbose > 1:
            pytest.reporter.line(get_item_nodeid(item) + " step " + str(step) + " " + status.upper())


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
        "Pass": 0x7,  # 0111
        "In Progress": 0x3,  # 0011
        "Blocked": 0x1,  # 0001
        "Fail": 0x0  # 0000
    }
    if not step_results:
        return "Not Executed"
    status = 0xF
    for result in step_results:
        status &= status_map[result["status"]]

    return [k for k, v in status_map.items() if v == status][0]


def create_report(test_case_key, test_step_key, execute_time, skip_status, passed, test_result_data, specs=None):
    """Generate adaptavist test results for given item.

        :param test_case_key: The test case to report.
        :param test_step_key: The test step to report.
        :param execute_time: The time spent for execution.
        :param skip_status: pytest marker, may hold either a pytest.mark.skip or pytest.mark.block
        :param passed: True or False, depending on test result.
        :param test_result_data: additional data containing comments, attachments, etc.
    """
    test_run_key = pytest.test_run_key

    if test_run_key and test_case_key in (pytest.test_case_keys or []):

        adaptavist = pytest.adaptavist

        test_result = adaptavist.get_test_result(test_run_key, test_case_key)

        if not test_result or pytest.test_refresh_info[test_case_key + (specs or "")] != test_run_key:
            # create new test result to prevent accumulation of data
            # when using an existing test run key multiple times
            adaptavist.create_test_result(test_run_key=test_run_key, test_case_key=test_case_key, environment=pytest.test_environment, status=None)

            # refetch result
            test_result = adaptavist.get_test_result(test_run_key, test_case_key)

            pytest.test_refresh_info[test_case_key + (specs or "")] = test_run_key

        # touch parametrized/repeated items
        for key in pytest.test_refresh_info:
            if re.search(test_case_key + r"[ \[\b]", key):
                pytest.test_refresh_info[key] = pytest.test_run_key

        # get optional meta data (comments, attachments) of test case method
        comment = skip_status.kwargs.get("reason") if skip_status else test_result_data.get("comment")
        description = None if skip_status else test_result_data.get("description")
        attachment = None if skip_status else test_result_data.get("attachment")

        header = f"---------------------------------------- {datetime.now().strftime('%Y%m%d%H%M')} ----------------------------------------" if specs else ""

        if not skip_status and not test_step_key:
            # update test case with CI related info
            adaptavist.edit_test_case(test_case_key,
                                      labels=["automated"],
                                      build_urls=[(pytest.build_url if not pytest.build_url else f"<a href=\"{pytest.build_url}\">{pytest.build_url}</a>") or ""],
                                      code_bases=[(pytest.code_base if not pytest.code_base else f"<a href=\"{pytest.code_base}\">{pytest.code_base}</a>") or ""])

        if test_step_key:

            # in case of parameterization or repetition the status will be Fail if one iteration failed
            last_result = next((result for result in test_result.get("scriptResults", []) if result["index"] == int(test_step_key) - 1), {})

            if skip_status and last_result.get("status", None) != "Fail":
                status = "Blocked" if skip_status.name == "block" else "Not Executed"
            else:
                status = "Pass" if passed and last_result.get("status", None) != "Fail" else "Fail"

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + (last_result.get("comment", "") if specs else "")

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
                comments = ("step {0} {1}:".format(test_step_key, "blocked" if skip_status.name == "block" else "skipped") +
                            (("<br>" + comment + "<br>") if comment else ""))
            elif not passed:
                # modify comment to add info about failure in script steps
                comments = ("step {0} failed:".format(test_step_key) + (("<br>" + comment + "<br>") if comment else ""))

            # find the right position to insert comments of this test execution (in case of parametrized or repeated test methods)
            index = test_result.get("comment", "").find("---------------------------------------- ")

            adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                               test_case_key=test_case_key,
                                               environment=pytest.test_environment,
                                               status=status,
                                               comment=(test_result.get("comment", "") + (comments or "")) if index < 0 else
                                               (test_result.get("comment", "")[:index] + (comments or "") + test_result.get("comment", "")[index:]),
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
            elif status == "Not Executed":
                status = "Pass" if passed else "Fail"

            comments = ((header + "<br>" + "parameterization " + (specs or "") + "<br><br>") if specs else "") + ((comment + "<br>") if comment else "") + (
                (description + "<br>") if description else "") + test_result.get("comment", "")

            result_id = adaptavist.edit_test_result_status(test_run_key=test_run_key,
                                                           test_case_key=test_case_key,
                                                           environment=pytest.test_environment,
                                                           status=status,
                                                           comment=comments,
                                                           execute_time=execute_time)

            if attachment:
                adaptavist.add_test_result_attachment(test_result_id=result_id, attachment=attachment, filename=test_result_data.get("filename", None))


def get_item_name_and_spec(nodeid):
    """Split item nodeid into function name and - if existing - callspec res. parameterization."""
    tokens = nodeid.split("[", 1)
    return tokens[0].strip(), "[" + tokens[1].strip() if len(tokens) > 1 else None


def get_item_nodeid(item):
    """Build item node id."""
    # note: pytest's item.nodeid could be modified by third party, so build a local one here
    if item.location and len(item.location) > 2:
        return item.location[0].replace("\\", "/") + "::" + item.location[2].replace(".", "::")
    return item.fspath.relto(item.config.rootdir).replace("\\", "/") + "::" + item.getmodpath().replace(".", "::")


def get_marker(item, name):
    """Get item marker (wrapper for supporting older and newer pytest versions)."""
    return (getattr(item, "get_closest_marker", None) or getattr(item, "get_marker", None))(name)


def get_status_color(status):
    """Return (markup) color for test result status."""
    colormap = {
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

    return colormap.get(status, {})


def html_row(condition, message):
    """Generate an html status row to be displayed in test case results."""
    return f"<div style='padding: 2pt'><span style='width: auto; margin-right: 4pt; padding: 2pt; border-radius: 4px; background-color: {'rgb(58, 187, 75)' if condition else 'rgb(223, 47, 54)'}; color: white; font-family: monospace; font-size: 10pt; font-weight: bold;'>{'PASS' if condition else 'FAIL'}</span>{message}</div>" if message else None


def import_module(module_name):
    """Import and return module if existing."""

    try:
        return pytest.importorskip(module_name)
    except pytest.skip.Exception:
        return None
