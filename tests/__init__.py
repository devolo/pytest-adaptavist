"""Unit and system tests."""

from __future__ import annotations

import json
from typing import Any, Tuple
from unittest.mock import MagicMock

import requests
from _pytest.pytester import HookRecorder

from pytest_adaptavist._atm_configuration import ATMConfiguration

AdaptavistMock = Tuple[MagicMock, MagicMock, MagicMock]


def system_test_preconditions() -> bool:
    """Check preconditions for system tests."""
    atmcfg = ATMConfiguration()
    if not atmcfg.config or \
       "project_key" not in atmcfg.config or \
       "jira_server" not in atmcfg.config or \
       "jira_username" not in atmcfg.config or \
       "jira_password" not in atmcfg.config:
        return False

    try:
        requests.adapters.DEFAULT_RETRIES = 1
        requests.get(atmcfg.config.get("jira_server"), timeout=1)
        return True
    except Exception:  # pylint: disable=broad-except
        return False


def get_test_values(report: HookRecorder, test_case: str = "") -> tuple[str, str]:
    """Get test run key and test case name."""
    user_properties = dict(report.matchreport(test_case).user_properties)
    test_run_key = user_properties["atmcfg"]["test_run_key"]
    test_name = user_properties["report"]["test_case_key"]
    return test_run_key, test_name


def read_global_config() -> dict[str, Any]:
    """Read global config and return as JSON."""
    with open("config/global_config.json", encoding="UTF-8") as f:
        config = json.loads(f.read())
    return config
