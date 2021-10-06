import os
from unittest.mock import patch

import pytest

pytest_plugins = "pytester"


@pytest.fixture(autouse=True)
def config_folder(pytester):
    pytester.mkdir("config")
    with open("config/global_config.json", "w") as f:
        f.write('{"project_key": "TEST", "test_run_key":"TEST-C1"}')
    os.environ["JIRA_SERVER"] = "https://test.com"


@pytest.fixture()
def adaptavist():
    with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"status": "Pass", "index": "0"}], "status": "Pass"}), \
         patch("adaptavist.Adaptavist.get_test_run", return_value={"items": [{"testCaseKey": "TEST-T123"}]}), \
         patch("adaptavist.Adaptavist.get_test_cases", return_value=[{"key": "TEST-T123"}]), \
         patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={"key": "TEST_RUN_TEST"}), \
         patch("pytest_adaptavist.atm_user_is_valid", return_value=True), \
         patch("adaptavist.Adaptavist.get_test_case", return_value={"name": "TEST-T123", "priority": "Normal"}), \
         patch("adaptavist.Adaptavist.edit_test_case", return_value=True), \
         patch("adaptavist.Adaptavist.create_test_result") as ctr, \
         patch("adaptavist.Adaptavist.edit_test_result_status") as etrs, \
         patch("adaptavist.Adaptavist.edit_test_script_status") as etss:
        yield ctr, etrs, etss
