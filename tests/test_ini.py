"""Test pytest.ini configuration."""
import pytest


@pytest.mark.usefixtures("adaptavist_mock")
class TestIniConfig:
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
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) in (
            "C1",
            ["C1"],
        )  # pylint: disable=protected-access

        result = pytester.runpytest("--adaptavist", plugins=["adaptavist", "assume"])
        assert "warnings" not in result.parseoutcomes()

        monkeypatch.setenv(option, "C2")
        report = pytester.inline_run("--adaptavist", plugins=["adaptavist", "assume"])
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) in (
            "C2",
            ["C2"],
        )  # pylint: disable=protected-access
