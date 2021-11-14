"""Test decorator usage."""

import pytest
from adaptavist import Adaptavist

from . import get_test_values, read_global_config, system_test_preconditions


@pytest.mark.usefixtures("configure")
class TestDecoratorUnit:
    """Test decorator usage on unit test level."""

    @pytest.mark.parametrize("marker", ["mark.block", "mark.project", "mark.testcase"])
    def test_adaptavist_markers(self, pytester: pytest.Pytester, marker: str):
        """Test registration of custom markers."""
        result = pytester.runpytest("--markers")
        assert any(marker in line for line in result.stdout.lines)

    @pytest.mark.usefixtures("adaptavist_mock")
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

        pytester.makepyfile("""
            import pytest

            @pytest.mark.block()
            class TestDummy:
                def test_dummy1():
                    assert True

                def test_dummy2():
                    assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["blocked"] == 2
        assert "passed" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_decorator_preferation(self, pytester: pytest.Pytester):
        """Test class block decorator is preferred to method decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.block()
            class TestClass:

                @pytest.mark.skip()
                def test_dummy(self):
                    assert True
        """)
        report = pytester.runpytest("--adaptavist")
        outcome = report.parseoutcomes()
        assert outcome["blocked"] == 1
        assert "passed" not in outcome


@pytest.mark.system
@pytest.mark.skipif(not system_test_preconditions(), reason="Preconditions for system tests not met. Please see README.md")
class TestDecoratorSystem:
    """Test decorator usage on system test level."""

    def test_T5(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test blocking decorator."""
        pytester.makepyfile("""
            import pytest

            def test_T4(meta_block):  # As a blocked Testcase has no test_run attached, we need another test case to get the test_run_key
                with meta_block() as mb:
                    mb.check(True)

            @pytest.mark.block
            def test_T5(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False)
                with meta_block(2) as mb_2:
                    mb_2.check(False)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, _ = get_test_values(report, "test_T4")
        config = read_global_config()
        test_result = adaptavist.get_test_result(test_run_key, f"{config['project_key']}-T5")
        assert test_result["status"] == "Blocked"
        assert test_result["scriptResults"][0]["status"] == "Not Executed"
