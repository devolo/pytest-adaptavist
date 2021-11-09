from adaptavist.const import STATUS_NOT_EXECUTED

from pytest_adaptavist._helpers import calc_test_result_status, html_row


def test_calc_test_result_status_empty():
    assert calc_test_result_status([]) == STATUS_NOT_EXECUTED


def test_html_row_early_return():
    assert html_row(True, "") == ""
    assert html_row(False, "") == ""
