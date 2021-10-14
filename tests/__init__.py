"""Unit and system tests."""

from typing import Tuple
from unittest.mock import MagicMock

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

    return True
