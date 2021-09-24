"""Helper methods used by the module."""

import subprocess
from contextlib import suppress
from typing import Dict, List, Optional

import pytest
from _pytest.nodes import Item
from _pytest.python import Function
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from adaptavist.const import STATUS_BLOCKED, STATUS_FAIL, STATUS_IN_PROGRESS, STATUS_NOT_EXECUTED, STATUS_PASS


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
        STATUS_NOT_EXECUTED: 0xB,  # 1011
        STATUS_PASS: 0x7,  # 0111
        STATUS_IN_PROGRESS: 0x3,  # 0011
        STATUS_BLOCKED: 0x1,  # 0001
        STATUS_FAIL: 0x0  # 0000
    }
    if not step_results:
        return STATUS_NOT_EXECUTED
    status = 0xF
    for result in step_results:
        status &= status_map[result["status"]]

    return [k for k, v in status_map.items() if v == status][0]


def get_code_base_url() -> Optional[str]:
    """Get current code base url."""
    code_base = None
    with suppress(subprocess.CalledProcessError):
        code_base = subprocess.check_output("git config --get remote.origin.url".split()).decode("utf-8").strip()
    return code_base


def get_spec(nodeid: str) -> Optional[str]:
    """Split item nodeid - if existing - callspec res. parameterization."""
    tokens = nodeid.split("[", 1)
    return "[" + tokens[1].strip() if len(tokens) > 1 else None


def get_item_nodeid(item: Item) -> str:
    """Build item node id."""
    # note: pytest's item.nodeid could be modified by third party, so build a local one here
    if item.location and len(item.location) > 2:
        return item.location[0].replace("\\", "/") + "::" + item.location[2].replace(".", "::")
    return item.fspath.relto(item.config.rootdir).replace("\\", "/") + "::" + item.getmodpath().replace(".", "::")


def html_row(condition: bool, message: str) -> str:
    """Generate an html status row to be displayed in test case results."""
    if not message:
        return ""

    if condition:
        background_color = "rgb(58, 187, 75)"
        badge_text = STATUS_PASS
    else:
        background_color = "rgb(223, 47, 54)"
        badge_text = STATUS_FAIL

    return f"<div style='padding: 2pt'><span style='width: auto; margin-right: 4pt; padding: 2pt; border-radius: 4px; background-color: {background_color}; \
            color: white; font-family: monospace; font-size: 10pt; font-weight: bold;'>{badge_text}</span>{message}</div>"


def intersection(list_a: List, list_b: List) -> List:
    """Return the intersection of two lists (maintaining the item order of the first list)."""
    return sorted(set(list_a) & set(list_b), key=list_a.index)


def apply_test_case_range(collected_items: Dict[str, List[Function]], test_case_range: List[str]) -> Dict[str:List[Function]]:
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


def handle_failed_assumptions(item: Item, call: CallInfo, report: TestReport):
    """Handle failed assumptions (simulating pytest-assume, if not available)."""

    if hasattr(pytest, "assume"):
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
