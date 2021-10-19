"""Fixtures for tests."""

import json
import os
import shutil
from typing import Generator
from unittest.mock import patch

import pytest
from adaptavist import Adaptavist

from . import AdaptavistFixture

pytest_plugins = ("pytester", )


def pytest_configure(config):
    config.addinivalue_line("markers", "system: mark test as system tests. Select system tests with '-m system'")


@pytest.fixture()
def configure_global_config(pytester: pytest.Pytester):
    pytester.copy_example("config/global_config.json")
    os.mkdir("config")
    shutil.move("global_config.json", "config/global_config.json")
    with open("config/global_config.json") as f:
        config = json.loads(f.read())
    a: Adaptavist = Adaptavist(config["jira_server"], config["jira_username"], config["jira_password"])
    yield a


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
