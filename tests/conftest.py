"""Fixtures for tests."""

import json
import os
import shutil
from contextlib import suppress
from typing import Generator
from unittest.mock import patch

import pytest
from adaptavist import Adaptavist

from . import AdaptavistFixture, system_test_preconditions

pytest_plugins = ("pytester", )


def pytest_configure(config):
    config.addinivalue_line("markers", "system: mark test as system tests. Select system tests with '-m system'")


def pytest_sessionfinish():
    if system_test_preconditions():
        with suppress(FileNotFoundError):
            os.remove("config/global_config_copy.json")


@pytest.fixture()
def atm(pytester: pytest.Pytester):
    with suppress(KeyError):
        del os.environ['JIRA_SERVER']
    pytester.copy_example("config/global_config_copy.json")
    pytester.mkdir("config")
    shutil.move("global_config_copy.json", "config/global_config.json")
    with open("config/global_config.json") as f:
        config = json.loads(f.read())
    atm_obj: Adaptavist = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
    yield atm_obj


@pytest.fixture()
def atm_test_plan(pytester: pytest.Pytester):
    with suppress(KeyError):
        del os.environ['JIRA_SERVER']
    pytester.copy_example("config/global_config_copy.json")
    pytester.mkdir("config")
    shutil.move("global_config_copy.json", "config/global_config.json")
    with open("config/global_config.json", "r", encoding="utf8") as f:
        config = json.loads(f.read())
    atm_obj: Adaptavist = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
    test_run = atm_obj.create_test_run(config["project_key"], "just a name")
    config["test_run_key"] = test_run
    with open("config/global_config.json", "w", encoding="utf8") as f:
        f.write(json.dumps(config))
    atm_obj: Adaptavist = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
    yield atm_obj, test_run


# This should only be used if test is a system test
@pytest.fixture(scope="session", autouse=True)
def test_plan(request):
    """Creates a test plan. All system test will link the test cycle with this test plan."""
    if system_test_preconditions():
        with open("config/global_config.json", "r", encoding="utf8") as f:
            config = json.loads(f.read())
            atm_obj: Adaptavist = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
            test_plan = atm_obj.create_test_plan(config["project_key"], "just a test plan name")
            config["test_plan_key"] = test_plan
        with open("config/global_config_copy.json", "w", encoding="utf8") as f:
            f.write(json.dumps(config))


@pytest.fixture
def configure(pytester: pytest.Pytester):
    """Configure environment for unittests."""
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
def adaptavist(valid_user: None) -> Generator[AdaptavistFixture, None, None]:
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
         patch("adaptavist.Adaptavist.create_test_result") as ctr, \
         patch("adaptavist.Adaptavist.edit_test_result_status") as etrs, \
         patch("adaptavist.Adaptavist.edit_test_script_status") as etss:
        yield ctr, etrs, etss
