"""Unit and system tests."""

from typing import Tuple
from unittest.mock import MagicMock
import requests
from _pytest.pytester import HookRecorder
from pytest_adaptavist._atm_configuration import ATMConfiguration

AdaptavistFixture = Tuple[MagicMock, MagicMock, MagicMock]


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


def get_test_values(report: HookRecorder, test_case: str = ""):
    user_properties = dict(report.matchreport(test_case).user_properties)
    test_run_key = user_properties["atmcfg"]["test_run_key"]
    test_name = user_properties["report"]["test_case_key"]
    return test_run_key, test_name
