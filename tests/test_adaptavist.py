"""Test compatibility with Adaptavist."""

import getpass
import logging
from unittest.mock import patch

import pytest

from . import AdaptavistMock


@pytest.mark.usefixtures("configure")
class TestAdaptavistUnit:
    """Test compatibility with Adaptavist on unit test level."""

    def test_adaptavist_reporting(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test reporting results to Adaptavist."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123():
                assert True
        """)
        ctr, _, _ = adaptavist_mock
        pytester.runpytest("--adaptavist")
        ctr.assert_called_once_with(test_run_key="TEST-C1",
                                    test_case_key="TEST-T123",
                                    environment=None,
                                    executor=getpass.getuser().lower(),
                                    assignee=getpass.getuser().lower())

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_unknown_user(self, pytester: pytest.Pytester, caplog: pytest.LogCaptureFixture):
        """Test the correct behavior of an unknown user."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123():
                assert True
        """)
        with patch("pytest_adaptavist.atm_user_is_valid", return_value=False):
            pytester.runpytest("--adaptavist")
            assert caplog.records[-1].funcName == "pytest_configure"
            assert caplog.records[-1].levelno == logging.WARN
            assert caplog.records[-1].msg == "Local user '%s' is not known in Jira. Test cases will be reported without an executor!"

    def test_test_case_name_step(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test reporting results to Adaptavist if the step is set in testcase name."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123_1():
                assert True
        """)
        _, _, etss = adaptavist_mock
        pytester.runpytest("--adaptavist")
        etss.assert_called_once_with(test_run_key="TEST-C1",
                                     test_case_key="TEST-T123",
                                     step=1,
                                     status="Pass",
                                     comment="",
                                     environment=None,
                                     executor=getpass.getuser().lower(),
                                     assignee=getpass.getuser().lower())
