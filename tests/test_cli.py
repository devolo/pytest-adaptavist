"""Test CLI behavior."""

import os

import pytest
from _pytest.config import ExitCode


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

        pytester.makeini("""
            [pytest]
            adaptavist = 1
        """)
        config = pytester.parseconfig()
        assert config.getini("adaptavist")

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_invalid_branch(self, pytester: pytest.Pytester):
        """Test the correct behavior of an invalid branch."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123():
                assert True
        """)
        os.environ["GIT_BRANCH"] = "test"
        report = pytester.runpytest("--adaptavist", "--restrict-branch")
        assert report.ret == ExitCode.INTERNAL_ERROR
        report = pytester.runpytest("--restrict-branch")
        assert report.ret == ExitCode.OK
        report = pytester.runpytest("--adaptavist", "--restrict-branch", "--restrict-branch-name=test")
        assert report.ret == ExitCode.OK
        os.environ["GIT_BRANCH"] = "origin/master"
        report = pytester.runpytest("--adaptavist", "--restrict-branch")
        assert report.ret == ExitCode.OK
