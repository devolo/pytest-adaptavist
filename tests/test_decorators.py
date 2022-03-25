"""Test decorator usage."""

import pytest
from adaptavist import Adaptavist

from . import AdaptavistMock, get_test_values, read_global_config, system_test_preconditions


class TestDecoratorUnit:
    """Test decorator usage on unit test level."""

    @pytest.mark.parametrize("marker", ["mark.block", "mark.project", "mark.testcase"])
    def test_adaptavist_markers(self, pytester: pytest.Pytester, marker: str):
        """Test registration of custom markers."""
        result = pytester.runpytest("--markers")
        assert any(marker in line for line in result.stdout.lines)

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_block_decorator_with_class_decorator(self, pytester: pytest.Pytester):
        """Test block decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.parametrize("a", [1,2])
            class Test:
                @pytest.mark.block()
                def test_dummy(self, a):
                    assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["blocked"] == 2
        assert "passed" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_block_decorator_with_two_class_decorators(self, pytester: pytest.Pytester):
        """Test block decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.parametrize("a", [1,2])
            @pytest.mark.skipif(True)
            class Test:
                @pytest.mark.block()
                def test_dummy(self, a):
                    assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["skipped"] == 2
        assert "passed" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_block_decorator_with_class_skipif_decorator(self, pytester: pytest.Pytester):
        """Test block decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.skipif(True)
            class Test:
                @pytest.mark.block()
                def test_dummy(self):
                    assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["skipped"] == 1
        assert "passed" not in outcome
        assert "blocked" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
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

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_blockif_decorator(self, pytester: pytest.Pytester):
        """Test blockif decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.blockif(True, reason="Test")
            def test_dummy():
                assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["blocked"] == 1
        assert "passed" not in outcome

        pytester.makepyfile("""
            import pytest

            @pytest.mark.blockif(True, reason="Test")
            class Test:
                def test_dummy():
                    assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["blocked"] == 1
        assert "passed" not in outcome

        pytester.makepyfile("""
            import pytest

            @pytest.mark.blockif(False, reason="Test")
            def test_dummy():
                assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["passed"] == 1
        assert "blocked" not in outcome

        pytester.makepyfile("""
            import pytest

            @pytest.mark.blockif(False, True, reason="Test")
            def test_dummy():
                assert True
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["blocked"] == 1
        assert "passed" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
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

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_decorator_combination_blocked(self, pytester: pytest.Pytester):
        """Test class block decorator is useful combined with method decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.blockif(False, reason="asdasd")
            class TestClass:

                @pytest.mark.block()
                def test_dummy(self):
                    assert True
        """)
        report = pytester.runpytest("--adaptavist")
        outcome = report.parseoutcomes()
        assert outcome["blocked"] == 1
        assert "passed" not in outcome

    @pytest.mark.usefixtures("adaptavist_mock", "configure")
    def test_multiple_skipif(self, pytester: pytest.Pytester):
        """Test multiple conditions in a skipif decorator."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.skipif(False, True, reason="Test")
            def test_dummy(self):
                assert True
        """)
        report = pytester.runpytest("--adaptavist")
        outcome = report.parseoutcomes()
        assert outcome["skipped"] == 1
        assert "passed" not in outcome

    def test_project_decorator(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test project decorator."""
        pytester.makepyfile("""
            import pytest

            class TestClass:
                @pytest.mark.project(project_key="MARKER")
                def test_T16(self):
                    assert True
        """)
        _, etrs, _ = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert etrs.call_args.kwargs["test_case_key"] == "MARKER-T16"

    @pytest.mark.usefixtures("configure")
    def test_respect_project_decorator_if_project_key_set(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Respect a project key if set in a config file."""
        pytester.makepyfile("""
            import pytest

            class TestClass():
                def test_T1(self, meta_block):
                    pass

                @pytest.mark.project(project_key="TEST")
                def test_T17(self, meta_block):
                    pass
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{"project_key": "OTHERTEST"}')
        _, etrs, _ = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert etrs.call_args_list[0].kwargs["test_case_key"] == "OTHERTEST-T1"
        assert etrs.call_args_list[1].kwargs["test_case_key"] == "TEST-T17"


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

    def test_T38(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test blockif decorator."""
        pytester.makepyfile("""
            import pytest

            def test_T4(meta_block):  # As a blocked Testcase has no test_run attached, we need another test case to get the test_run_key
                with meta_block() as mb:
                    mb.check(True)

            @pytest.mark.blockif(True, reason="blockif reason")
            def test_T38(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False)
                with meta_block(2) as mb_2:
                    mb_2.check(False)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, _ = get_test_values(report, "test_T4")
        config = read_global_config()
        test_result = adaptavist.get_test_result(test_run_key, f"{config['project_key']}-T38")
        assert test_result["status"] == "Blocked"
        assert "blockif reason" in test_result["comment"]
        assert test_result["scriptResults"][0]["status"] == "Not Executed"
