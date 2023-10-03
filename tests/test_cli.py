"""Test CLI behavior."""
import pytest
from _pytest.config import ExitCode
from _pytest.pytester import LineMatcher


@pytest.mark.usefixtures("configure")
class TestCliUnit:
    """Test CLI behavior on unit test level."""

    def test_adaptavist_disabled(self, pytester: pytest.Pytester):
        """Test absence of adaptavist config if disabled."""
        config = pytester.parseconfig()
        assert not config.getoption("adaptavist")
        assert not config.getini("adaptavist")

    def test_adaptavist_enabled(self, pytester: pytest.Pytester):
        """Test presence of adaptavist config if enabled."""
        config = pytester.parseconfig("--adaptavist")
        assert config.getoption("adaptavist")

        pytester.makeini(
            """
            [pytest]
            adaptavist = 1
        """
        )
        config = pytester.parseconfig()
        assert config.getini("adaptavist")

    def test_cycle_info_urls(self, pytester: pytest.Pytester):
        """Test that the cycle information urls are build correctly."""
        pytester.makepyfile(
            """
            import pytest

            def test_TEST_T123():
                assert True
        """
        )
        report = pytester.runpytest("--adaptavist")
        matcher = LineMatcher(report.outlines)

        #pylint: disable=line-too-long
        matcher.fnmatch_lines(
            [
                "traceability:  https://jira.test/secure/Tests.jspa#/reports/traceability/report/view?tql=testResult.projectKey%20IN%20%28%22TEST%22%29%20AND%20testRun.key%20IN%20%28%22TEST-C1%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TRACEABILITY_REPORT.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS",
                "test_summary:  https://jira.test/secure/Tests.jspa#/reports/testresults/board/view?tql=testResult.projectKey%20IN%20%28%22TEST%22%29%20AND%20testRun.key%20IN%20%28%22TEST-C1%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_BOARD.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS",
                "score_matrix:  https://jira.test/secure/Tests.jspa#/reports/testresults/scorecard/coverage/view?tql=testResult.projectKey%20IN%20%28%22TEST%22%29%20AND%20testRun.key%20IN%20%28%22TEST-C1%22%29%20AND%20testRun.onlyLastTestResult%20IS%20true&jql=&title=REPORTS.TEST_RESULTS_SCORECARD_BY_COVERAGE.TITLE&traceabilityReportOption=COVERAGE_TEST_CASES&traceabilityTreeOption=COVERAGE_TEST_CASES&traceabilityMatrixOption=COVERAGE_TEST_CASES&period=MONTH&scorecardOption=EXECUTION_RESULTS",
            ]
        )

    def test_invalid_branch(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
        """Test the correct behavior of an invalid branch."""
        pytester.makepyfile(
            """
            import pytest

            def test_TEST_T123():
                assert True
        """
        )
        monkeypatch.setenv("GIT_BRANCH", "test")
        report = pytester.runpytest("--adaptavist", "--restrict-branch")
        assert report.ret == ExitCode.INTERNAL_ERROR
        report = pytester.runpytest("--restrict-branch")
        assert report.ret == ExitCode.OK
        report = pytester.runpytest("--adaptavist", "--restrict-branch", "--restrict-branch-name=test")
        assert report.ret == ExitCode.OK
        monkeypatch.setenv("GIT_BRANCH", "origin/master")
        report = pytester.runpytest("--adaptavist", "--restrict-branch")
        assert report.ret == ExitCode.OK
