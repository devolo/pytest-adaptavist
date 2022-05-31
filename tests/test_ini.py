import os

import pytest


@pytest.mark.usefixtures("configure")
@pytest.mark.usefixtures("adaptavist_mock")
def test_atm_ini(pytester: pytest.Pytester):
    """Test if values in ini files are at the correct intern value and recognized by pytest."""
    pytester.makepyfile(
        """
            def test_T1(meta_block):
                with meta_block():
                    with meta_block(1) as mb_1:
                        mb_1.check(True)
        """
    )

    string_options = [
        "project_key",
        "test_plan_key",
        "test_plan_folder",
        "test_plan_suffix",
        "test_run_key",
        "test_run_folder",
        "test_run_suffix",
        "test_environment",
    ]
    for option in string_options:
        pytester.makeini(
            f"""
            [pytest]
            {option} = C1
        """
        )
        report = pytester.inline_run("--adaptavist")
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) == "C1"  # pylint: disable=protected-access

        report = pytester.runpytest("--adaptavist").parseoutcomes()
        with pytest.raises(KeyError):
            report["warnings"]

        os.environ[option] = "C2"
        report = pytester.inline_run("--adaptavist")
        del os.environ[option]
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) == "C2"  # pylint: disable=protected-access

    list_options = [
        "test_case_keys",
        "test_case_order",
        "test_case_range",
    ]

    for option in list_options:
        pytester.makeini(
            f"""
            [pytest]
            {option} = C1
        """
        )
        report = pytester.inline_run("--adaptavist")
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) == ["C1"]  # pylint: disable=protected-access

        report = pytester.runpytest("--adaptavist").parseoutcomes()
        with pytest.raises(KeyError):
            report["warnings"]

        os.environ[option] = "C2"
        report = pytester.inline_run("--adaptavist")
        del os.environ[option]
        assert getattr(report._pluginmanager.get_plugin("_adaptavist"), option) == ["C2"]  # pylint: disable=protected-access
