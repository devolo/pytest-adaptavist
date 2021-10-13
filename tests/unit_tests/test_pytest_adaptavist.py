""" Test connection between pytest and Adaptavist."""

from typing import Tuple
from unittest.mock import MagicMock, patch

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
    """Test the early return in create_report if config is not valid."""

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


def test_skipped_test_cases(pytester: pytest.Pytester, adaptavist: Tuple[MagicMock, MagicMock, MagicMock]):
    """Test that a skipped test case is reported as 'Not Executed'."""
    pytester.makepyfile("""
        import pytest

        @pytest.mark.skip()
        def test_T123(meta_block):
            with meta_block(1):
                assert True
    """)
    with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"index": "0"}]}):
        pytester.runpytest("--adaptavist")
    _, etrs, _ = adaptavist
    assert etrs.call_count == 1
    assert etrs.call_args.kwargs["status"] == "Not Executed"


def test_bcd(pytester: pytest.Pytester, adaptavist: Tuple[MagicMock, MagicMock, MagicMock]):
    """Test that a testcase is reported correctly. The steps must not reported in this test."""
    pytester.makepyfile("""
        import pytest

        def test_T123(meta_block):
            with meta_block() as mb:
                mb.check(True)
    """)
    pytester.runpytest("--adaptavist")
    _, etrs, _ = adaptavist
    assert etrs.call_count == 1
    assert etrs.call_args.kwargs["status"] == "Pass"


@pytest.mark.usefixtures("adaptavist")
def test_test_result_attachment(pytester: pytest.Pytester):
    """Test that an attachment is correctly attached to the testcase (not to the step)."""
    pytester.makepyfile("""
        import pytest

        def test_T123(meta_block):
            with meta_block() as mb:
                mb.check(True, attachment="ATTACHMENT", filename="test.txt")
    """)
    with patch("adaptavist.Adaptavist.add_test_result_attachment") as atra:
        pytester.runpytest("--adaptavist")
    assert atra.call_count == 1
    assert atra.call_args.kwargs["attachment"] == "ATTACHMENT"
    assert atra.call_args.kwargs["filename"] == "test.txt"
