"""Test general plugin functionality."""

from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize("marker", ["mark.block", "mark.project", "mark.testcase"])
def test_adaptavist_markers(pytester: pytest.Pytester, marker: str):
    """Test registration of custom markers."""
    result = pytester.runpytest("--markers")
    assert any(marker in line for line in result.stdout.lines)


def test_adaptavist_disabled(pytester: pytest.Pytester):
    """Test absence of adaptavist config if disabled."""
    config = pytester.parseconfig()
    assert not config.getoption("adaptavist")
    assert not config.getini("adaptavist")


def test_adaptavist_enabled(pytester: pytest.Pytester):
    """Test presence of adaptavist config if enabled."""
    config = pytester.parseconfig("--adaptavist")
    assert config.getoption("adaptavist")

    pytester.makeini("""
        [pytest]
        adaptavist = 1
    """)
    config = pytester.parseconfig()
    assert config.getini("adaptavist")


@pytest.mark.usefixtures("valid_user")
def test_block_decorator(pytester: pytest.Pytester, adaptavist):
    """Test block decorator."""
    pytester.makepyfile("""
        import pytest

        @pytest.mark.block()
        def test_dummy():
            assert True
    """)
    outcome = pytester.runpytest().parseoutcomes()
    assert outcome["blocked"] == 1
    assert "passed" not in outcome


@pytest.mark.usefixtures("valid_user")
def test_block_call(pytester: pytest.Pytester, adaptavist):
    """Test calling block."""
    pytester.makepyfile("""
        import pytest

        def test_dummy():
            pytest.block()
            assert True
    """)
    outcome = pytester.runpytest().parseoutcomes()
    assert outcome["blocked"] == 1
    assert "passed" not in outcome


# def test_xdist_handling(pytester):
#     pytester.makepyfile("""
#         import pytest
#         def test_dummy():
#             assert True
#     """)
#     with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
#         result = pytester.runpytest("--adaptavist")
#     assert any("reporting: enabled" in line for line in result.stdout.lines)


def test_adaptavist_reporting(pytester: pytest.Pytester, adaptavist: Tuple[MagicMock, MagicMock, MagicMock]):
    """Test reporting results to Adaptavist."""
    pytester.makepyfile("""
        import pytest

        def test_TEST_T123():
            assert True
    """)
    ctr, _, _ = adaptavist
    pytester.runpytest("--adaptavist")
    ctr.assert_called_once_with(test_run_key="TEST-C1", test_case_key="TEST-T123", environment="")


def test_unknown_user(pytester: pytest.Pytester, adaptavist: Tuple[MagicMock, MagicMock, MagicMock]):
    """Test the correct behaviour of an unknonwn user."""
    pytester.makepyfile("""
        import pytest

        def test_TEST_T123():
            assert True
    """)
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=False):
        report = pytester.runpytest("--adaptavist")
        assert any("is not known in Adaptavist" in x for x in report.outlines)

        report = pytester.runpytest()
        assert all(" is not known in Adaptavist" not in x for x in report.outlines)
