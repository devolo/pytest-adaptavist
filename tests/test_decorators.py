"""Test decorator usage."""

import pytest

from pytest_adaptavist import MetaBlockFixture

from . import system_test_preconditions


@pytest.mark.usefixtures("configure")
class TestDecoratorUnit:
    """Test decorator usage on unit test level."""

    @pytest.mark.parametrize("marker", ["mark.block", "mark.project", "mark.testcase"])
    def test_adaptavist_markers(self, pytester: pytest.Pytester, marker: str):
        """Test registration of custom markers."""
        result = pytester.runpytest("--markers")
        assert any(marker in line for line in result.stdout.lines)

    @pytest.mark.usefixtures("adaptavist")
    def test_block_decorator(self, pytester: pytest.Pytester):
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


@pytest.mark.skipif(not system_test_preconditions(), reason="Preconditions for system tests not met. Please see README.md")
class TestDecoratorSystem:
    """Test decorator usage on system test level."""

    @pytest.mark.block("TESTING BLOCK DECORATOR")
    def test_T5(self, meta_block: MetaBlockFixture):
        """Test block decorator."""
        with meta_block(1) as mb_1:
            mb_1.check(False)
