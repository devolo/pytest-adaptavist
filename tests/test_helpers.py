"""Test helper functions."""

from adaptavist.const import STATUS_BLOCKED, STATUS_FAIL, STATUS_IN_PROGRESS, STATUS_NOT_EXECUTED, STATUS_PASS
from bs4 import BeautifulSoup

from pytest_adaptavist._helpers import calc_test_result_status, html_row


class TestHelpersUnit:
    """Test helper functions on unit test level."""

    def test_calc_test_result_status(self):
        """Test calculation of test results."""
        assert calc_test_result_status([]) == STATUS_NOT_EXECUTED

        assert calc_test_result_status([{"status": STATUS_BLOCKED}, {"status": STATUS_NOT_EXECUTED}]) == STATUS_BLOCKED
        assert calc_test_result_status([{"status": STATUS_BLOCKED}, {"status": STATUS_IN_PROGRESS}]) == STATUS_BLOCKED
        assert calc_test_result_status([{"status": STATUS_BLOCKED}, {"status": STATUS_PASS}]) == STATUS_BLOCKED
        assert calc_test_result_status([{"status": STATUS_BLOCKED}, {"status": STATUS_FAIL}]) == STATUS_FAIL

        assert calc_test_result_status([{"status": STATUS_FAIL}, {"status": STATUS_NOT_EXECUTED}]) == STATUS_FAIL
        assert calc_test_result_status([{"status": STATUS_FAIL}, {"status": STATUS_IN_PROGRESS}]) == STATUS_FAIL
        assert calc_test_result_status([{"status": STATUS_FAIL}, {"status": STATUS_PASS}]) == STATUS_FAIL

        assert calc_test_result_status([{"status": STATUS_PASS}, {"status": STATUS_NOT_EXECUTED}]) == STATUS_IN_PROGRESS
        assert calc_test_result_status([{"status": STATUS_PASS}, {"status": STATUS_IN_PROGRESS}]) == STATUS_IN_PROGRESS

        assert calc_test_result_status([{"status": STATUS_IN_PROGRESS}, {"status": STATUS_NOT_EXECUTED}]) == STATUS_IN_PROGRESS

    def test_html_row(self):
        """Test html status row to be displayed in test case results."""
        assert html_row("passed", "") == ""
        assert html_row("failed", "") == ""
        assert html_row("blocked", "") == ""

        span = BeautifulSoup(html_row("passed", "Testmessage"), features="lxml").find("span")
        assert span.text == STATUS_PASS
        assert span.next_sibling == "Testmessage"
        assert "rgb(58, 187, 75)" in span.attrs["style"]

        span = BeautifulSoup(html_row("failed", "Testmessage"), features="lxml").find("span")
        assert span.text == STATUS_FAIL
        assert span.next_sibling == "Testmessage"
        assert "rgb(223, 47, 54)" in span.attrs["style"]

        span = BeautifulSoup(html_row("blocked", "Testmessage"), features="lxml").find("span")
        assert span.text == STATUS_BLOCKED
        assert span.next_sibling == "Testmessage"
        assert "rgb(75, 136, 231)" in span.attrs["style"]
