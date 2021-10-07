"""Fixtures for tests."""

import os
from typing import Generator, Tuple
from unittest.mock import MagicMock, patch

import pytest

pytest_plugins = ("pytester",)


@pytest.fixture(autouse=True)
def configure(pytester: pytest.Pytester):
    """Configure environment."""
    pytester.mkdir("config")
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write('{"project_key": "TEST", "test_run_key":"TEST-C1"}')
    os.environ["JIRA_SERVER"] = "https://test.com"


@pytest.fixture
def valid_user() -> Generator[None, None, None]:
    """Mark user as always valid."""
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        yield


@pytest.fixture
def adaptavist(valid_user: None) -> Generator[Tuple[MagicMock, MagicMock, MagicMock], None, None]:
    """Patch adapvavist to prevent real I/O."""
    with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"status": "Pass", "index": "0"}], "status": "Pass"}), \
         patch("adaptavist.Adaptavist.get_test_run", return_value={"items": [{"testCaseKey": "TEST-T123"}]}), \
         patch("adaptavist.Adaptavist.get_test_cases", return_value=[{"key": "TEST-T123"}]), \
         patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={"key": "TEST_RUN_TEST"}), \
         patch("adaptavist.Adaptavist.get_test_case", return_value={"name": "TEST-T123", "priority": "Normal"}), \
         patch("adaptavist.Adaptavist.edit_test_case", return_value=True), \
         patch("adaptavist.Adaptavist.create_test_result") as ctr, \
         patch("adaptavist.Adaptavist.edit_test_result_status") as etrs, \
         patch("adaptavist.Adaptavist.edit_test_script_status") as etss:
        yield ctr, etrs, etss
