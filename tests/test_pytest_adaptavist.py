""" Test connection between pytest and Adaptavist."""

from typing import Tuple
from unittest.mock import MagicMock

import pytest


@pytest.mark.usefixtures("adaptavist")
def test_default_test_project(pytester: pytest.Pytester):
    """Test if a project is set to TEST if not found in markers, testcasename or config."""
    pytester.makepyfile("""
        import pytest

        def test_T123(meta_block):
            with meta_block(1):
                assert True
    """)
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write('{"test_run_key":"TEST-C1"}')
    hook_record = pytester.inline_run("--adaptavist")
    assert hook_record.matchreport().head_line == "test_T123"


@pytest.mark.usefixtures("adaptavist")
def test_skip_no_test_case_methods(pytester: pytest.Pytester):
    """Test if a test method which is not a valid adaptavist test case is skipped, if 'skip_ntc_methods' is set"""
    pytester.makepyfile("""
        import pytest

        def test_not_a_test_case(meta_block):
            with meta_block(1):
                assert True
    """)
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write('{"skip_ntc_methods": true}')
    report = pytester.runpytest("--adaptavist")
    assert report.parseoutcomes()["blocked"] == 1


def test_early_return_on_no_config(pytester: pytest.Pytester, adaptavist: Tuple[MagicMock, MagicMock, MagicMock]):
    """Test the early return in pytest_collection_modifyitems if config can not be loaded."""

    # TODO: How can atm_configure ever be False?
    pytester.makepyfile("""
        import pytest

        def test_T123(meta_block):
            with meta_block(1):
                assert True
    """)
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write('{}')
    pytester.runpytest("--adaptavist")
    ctr, etrs, etss = adaptavist
    assert ctr.call_count == 0
    assert etrs.call_count == 0
    assert etss.call_count == 0
