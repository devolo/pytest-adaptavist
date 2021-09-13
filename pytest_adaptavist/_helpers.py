import inspect
import os
from typing import Dict, List, Optional

import pytest


def assume(expr: Exception, msg: Optional[str] = None, level: int = 1):
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
    path = os.path.relpath(filename)
    context = msg or contextlist[0].lstrip()
    if path and line and context:
        entry = "{path}:{line}: AssumptionFailure\n\t{context}".format(**locals())

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


def calc_test_result_status(step_results: List[Dict[str, str]]) -> str:
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


def html_row(condition, message):
    """Generate an html status row to be displayed in test case results."""
    if not message:
        return None

    if condition:
        background_color = "rgb(58, 187, 75)"
        badge_text = "PASS"
    else:
        background_color = "rgb(223, 47, 54)"
        badge_text = "FAIL"

    return f"<div style='padding: 2pt'><span style='width: auto; margin-right: 4pt; padding: 2pt; border-radius: 4px; background-color: {background_color}; color: white; font-family: monospace; font-size: 10pt; font-weight: bold;'>{badge_text}</span>{message}</div>"


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

def handle_failed_assumptions(item, call, report):
    """Handle failed assumptions (simulating pytest-assume, if not available)."""

    if hasattr(pytest, "assume") and pytest.assume is not assume:
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
