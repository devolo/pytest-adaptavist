"""Fixtures for tests."""

import os
import shutil
from typing import Generator
from unittest.mock import patch

import pytest
from _pytest.config import Config
from adaptavist import Adaptavist

from . import AdaptavistMock, read_global_config, system_test_preconditions

pytest_plugins = ("pytester", )


def pytest_configure(config: Config):
    """Configure pytest."""
    config.addinivalue_line("markers", "system: mark test as system tests. Select system tests with '-m system'")


@pytest.fixture(scope="session", autouse=True)
def create_test_plan(request):
    """Creates a test plan. All system test will link the test cycle with this test plan."""
    if system_test_preconditions() and request.config.option.markexpr != "not system":  # This should only be used if test is a system test
        config = read_global_config()
        atm = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
        test_plan = atm.create_test_plan(config["project_key"], "pytest_adaptavist_system_test")
        os.environ["TEST_PLAN_KEY"] = test_plan


@pytest.fixture
def adaptavist(pytester: pytest.Pytester) -> Generator[Adaptavist, None, None]:
    """Establish connection to Adaptavist."""
    pytester.copy_example("config/global_config.json")
    pytester.mkdir("config")
    shutil.move("global_config.json", "config/global_config.json")
    config = read_global_config()
    atm = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
    yield atm


@pytest.fixture(name="test_run")
def create_test_run(adaptavist: Adaptavist) -> Generator[str, None, None]:
    """Create a new test run."""
    config = read_global_config()
    test_run = adaptavist.create_test_run(config["project_key"], "pytest_system_tests")
    if test_run:
        os.environ["TEST_RUN_KEY"] = test_run
        yield test_run
        del os.environ["TEST_RUN_KEY"]


@pytest.fixture
def configure(pytester: pytest.Pytester):
    """Configure environment for unittests."""
    pytester.mkdir("config")
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write('{"jira_server": "https://jira.test", "project_key": "TEST", "test_run_key":"TEST-C1"}')


@pytest.fixture
def valid_user() -> Generator[None, None, None]:
    """Mark user as always valid."""
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        yield


@pytest.fixture
def adaptavist_mock(valid_user: None) -> Generator[AdaptavistMock, None, None]:
    """Patch adaptavist to prevent real I/O."""
    with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"status": "Pass", "index": "0"}], "status": "Pass"}), \
         patch("adaptavist.Adaptavist.get_test_run", return_value={"items": [{"testCaseKey": "TEST-T121"},
                                                                             {"testCaseKey": "TEST-T123"},
                                                                             {"testCaseKey": "TEST-T124"}
                                                                             ]}), \
         patch("adaptavist.Adaptavist.get_test_cases", return_value=[{"key": "TEST-T123"}]), \
         patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={"key": "TEST_RUN_TEST"}), \
         patch("adaptavist.Adaptavist.get_test_case", return_value={"name": "TEST-T123", "priority": "Normal"}), \
         patch("adaptavist.Adaptavist.edit_test_case", return_value=True), \
         patch("adaptavist.Adaptavist._delete"), \
         patch("adaptavist.Adaptavist._get"), \
         patch("adaptavist.Adaptavist._post"), \
         patch("adaptavist.Adaptavist._put"), \
         patch("adaptavist.Adaptavist.create_test_result") as ctr, \
         patch("adaptavist.Adaptavist.edit_test_result_status") as etrs, \
         patch("adaptavist.Adaptavist.edit_test_script_status") as etss:
        yield ctr, etrs, etss
