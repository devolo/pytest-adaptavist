"""Test compatibility with Adaptavist."""

import getpass
from unittest.mock import patch

import pytest
from _pytest.config import ExitCode

from . import AdaptavistFixture


@pytest.mark.usefixtures("configure")
class TestAdaptavistUnit:
    """Test compatibility with Adaptavist on unit test level."""

    def test_adaptavist_reporting(self, pytester: pytest.Pytester, adaptavist: AdaptavistFixture):
        """Test reporting results to Adaptavist."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123():
                assert True
        """)
        ctr, _, _ = adaptavist
        pytester.runpytest("--adaptavist")
        ctr.assert_called_once_with(test_run_key="TEST-C1",
                                    test_case_key="TEST-T123",
                                    environment="",
                                    executor=getpass.getuser().lower(),
                                    assignee=getpass.getuser().lower())

    @pytest.mark.xfail(msg="Test case needs a rework")
    @pytest.mark.usefixtures("adaptavist")
    def test_unknown_user(self, pytester: pytest.Pytester):
        """Test the correct behavior of an unknown user."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123():
                assert True
        """)
        with patch("pytest_adaptavist.atm_user_is_valid", return_value=False):
            report = pytester.runpytest("--adaptavist")
            assert report.ret == ExitCode.INTERNAL_ERROR
            report = pytester.runpytest()
            assert report.ret == ExitCode.OK
