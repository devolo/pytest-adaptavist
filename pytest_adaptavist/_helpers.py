"""Helper methods used by the module."""

from __future__ import annotations

import inspect
import re
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal

import pytest
from _pytest._io import TerminalWriter
from _pytest.config import Config
from _pytest.python import Function
from _pytest.terminal import TerminalReporter
from adaptavist.const import STATUS_BLOCKED, STATUS_FAIL, STATUS_IN_PROGRESS, STATUS_NOT_EXECUTED, STATUS_PASS

from .constants import COLORMAP


def calc_test_result_status(step_results: list[dict[str, str]]) -> str:
    """
    Calculate overall test result status from list of step results.

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


def get_code_base_url() -> str:
    """Get current code base url."""
    code_base = ""
    with suppress(subprocess.CalledProcessError):
        code_base = subprocess.check_output("git config --get remote.origin.url".split()).decode("utf-8").strip()
    return code_base


def get_option_ini(config: Config, value: str) -> Any:
    """Get option from cli or ini configuration."""
    return config.getoption(value) or config.getini(value)


def get_spec(nodeid: str) -> str:
    """Get callspec from item nodeid."""
    tokens = nodeid.split("[", 1)
    return "[" + tokens[1].strip() if len(tokens) > 1 else ""


def get_item_nodeid(item: pytest.Item) -> str:
    """Build item node id."""
    # note: pytest's item.nodeid could be modified by third party, so build a local one here
    if getattr(item, "location", False) and len(item.location) > 2:
        return item.location[0].replace("\\", "/") + "::" + item.location[2].replace(".", "::")
    return ""


def html_row(condition: Literal["passed", "failed", "blocked"], message: str) -> str:
    """Generate an html status row to be displayed in test case results."""
    if not message:
        return ""

    if condition == "passed":
        background_color = "rgb(58, 187, 75)"
        badge_text = STATUS_PASS
    elif condition == "failed":
        background_color = "rgb(223, 47, 54)"
        badge_text = STATUS_FAIL
    else:
        background_color = "rgb(75, 136, 231)"
        badge_text = STATUS_BLOCKED

    return f"<div style='padding: 2pt'><span style='width: auto; margin-right: 4pt; padding: 2pt; border-radius: 4px; background-color: {background_color}; \
            color: white; font-family: monospace; font-size: 10pt; font-weight: bold;'>{badge_text}</span>{message}</div>"


def intersection(list_a: list[Any], list_b: list[Any]) -> list[Any]:
    """Return the intersection of two lists (maintaining the item order of the first list)."""
    return sorted(set(list_a) & set(list_b), key=list_a.index)


def apply_test_case_range(collected_items: dict[str, list[Function]], test_case_range: list[str]) -> dict[str, list[Function]]:
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


def build_terminal_report(when: str, item: pytest.Function, step: int, status: Literal["passed", "failed", "skipped", "blocked"] | None = None, level: int = 1):
    """
    Generate terminal output.

    :param when: The call info ("setup", "call")
    :param item: The item to report
    :param status: The status ("passed", "failed", "skipped", "blocked")
    :param item: The step index to report
    :param level: The stack trace level (1 = the caller's level, 2 = the caller's caller level, 3 = ...)
    """

    terminal_reporter: TerminalReporter | None = item.config.pluginmanager.getplugin("terminalreporter")
    terminal_writer: TerminalWriter = item.config.get_terminal_writer()

    if terminal_reporter and item.config.option.verbose > 1:

        # extract doc string from source
        (frame, _, line, _, _) = inspect.stack()[level][0:5]
        source_list = inspect.getsourcelines(frame)
        source_code = "".join(source_list[0][line - source_list[1]:])
        docs = re.findall(r"^[\s]*\"\"\"(.*?)\"\"\"", source_code, re.DOTALL | re.MULTILINE | re.IGNORECASE)
        doc_string = inspect.cleandoc(docs[0]) if docs else ""

        if when == "setup":
            terminal_reporter.write_sep("-", "Step " + str(step), bold=True)
            terminal_reporter.write(doc_string + ("\n" if doc_string else ""))
        elif when == "call" and status:
            fill = terminal_writer.fullwidth - terminal_writer.width_of_current_line - 1
            terminal_reporter.write_line(status.upper().rjust(fill), **COLORMAP[status])


@dataclass
class Attachment():
    """Storage for attachments to be uploaded to Adaptavist."""

    attachment: BinaryIO
    """Content of the attachment."""

    filename: str
    """Filename of the attachment."""

    step: int = 0
    """Step to attach it to, 0 for the overall test case."""
