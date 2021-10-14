"""Unit and system tests."""

from typing import Tuple
from unittest.mock import MagicMock

from pytest_adaptavist._atm_configuration import ATMConfiguration

AdaptavistFixture = Tuple[MagicMock, MagicMock, MagicMock]


def system_test_preconditions() -> bool:
    """Check preconditions for system tests."""
    atmcfg = ATMConfiguration()

    if not atmcfg.config or \
       not "project_key" in atmcfg.config or \
       not "jira_server" in atmcfg.config or \
       not "jira_username" in atmcfg.config or \
       not "jira_password" in atmcfg.config:
        return False

    return True
