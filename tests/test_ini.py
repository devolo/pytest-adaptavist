"""Test pytest.ini configuration."""
import os
from importlib.metadata import version

import pytest
from adaptavist import Adaptavist

from pytest_adaptavist import PytestAdaptavist
from tests import get_test_values, read_global_config, system_test_preconditions


@pytest.mark.usefixtures("adaptavist_mock")
class TestIniConfigUnit:
    """Test pytest.ini configuration on unit test level."""

    @pytest.mark.parametrize(
        "option",
        [
            "project_key",
            "test_case_keys",
            "test_case_order",
            "test_case_range",
            "test_environment",
            "test_plan_folder",
            "test_plan_suffix",
            "test_plan_key",
            "test_run_folder",
            "test_run_key",
            "test_run_suffix",
        ],
    )
    def test_ini_config_strings(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, option: str):
        """Test that string values in pytest.ini are correctly used and recognized by pytest."""
        monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
        pytester.makepyfile(
            """
            def test_T1(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """
        )
        pytester.makeini(
            f"""
            [pytest]
            {option} = C1
            """
        )

        report = pytester.inline_run("--adaptavist", plugins=["adaptavist", "assume"])
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) in (  # pylint: disable=protected-access
            "C1",
            ["C1"],
        )

        result = pytester.runpytest("--adaptavist", plugins=["adaptavist", "assume"])
        assert "warnings" not in result.parseoutcomes()

        monkeypatch.setenv(option, "C2")
        report = pytester.inline_run("--adaptavist", plugins=["adaptavist", "assume"])
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) in (  # pylint: disable=protected-access
            "C2",
            ["C2"],
        )

    @pytest.mark.xfail(
        version("adaptavist") < "2.3.1",
        reason="Session usage was introduced in version 2.3.1.",
    )
    def test_jira_settings(self, pytester: pytest.Pytester) -> None:
        """Test that jira settings in pytest.ini are correctly used and recognized by pytest."""
        pytester.makepyfile(
            """
            def test_T1(meta_block):
            with meta_block(1) as mb_1:
            mb_1.check(True)
        """
        )
        pytester.makeini(
            """
            [pytest]
            jira_server = https://jira.test
            jira_username = username
            jira_password = password
        """
        )
        report = pytester.inline_run("--adaptavist", plugins=["adaptavist", "assume"])
        adaptavist: PytestAdaptavist = report._pluginmanager.get_plugin("_adaptavist")  # pylint: disable=protected-access
        assert adaptavist.adaptavist.jira_server == "https://jira.test"
        assert adaptavist.adaptavist._session.auth.username == "username"  # pylint: disable=protected-access
        assert adaptavist.adaptavist._session.auth.password == "password"  # pylint: disable=protected-access


@pytest.mark.system
@pytest.mark.skipif(not system_test_preconditions(), reason="Preconditions for system tests not met. Please see README.md")
class TestIniConfigSystem:
    """Test pytest.ini configuration on system test level."""

    def test_T1(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test passing a test."""
        pytester.makepyfile(
            """
            def test_T1(meta_block):
                with meta_block():
                    with meta_block(1) as mb_1:
                        mb_1.check(True)
        """
        )
        config = read_global_config()
        pytester.makeini(
            f"""
            [pytest]
            project_key = {config["project_key"]}
            jira_server = {config["jira_server"]}
            jira_username = {config["jira_username"]}
            jira_password = {config["jira_password"]}
        """
        )
        os.remove("config/global_config.json")
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Pass"
        assert test_result["scriptResults"][0]["status"] == "Pass"
