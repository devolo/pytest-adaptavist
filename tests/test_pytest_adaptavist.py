"""Test connection between pytest and Adaptavist."""

from unittest.mock import patch

import pkg_resources
import pytest

from pytest_adaptavist import MetaBlockFixture

from . import AdaptavistFixture, system_test_preconditions


@pytest.mark.usefixtures("configure")
class TestPytestAdaptavistUnit:
    """Test connection between pytest and Adaptavist on unit test level."""

    @pytest.mark.usefixtures("adaptavist")
    def test_block_call(self, pytester: pytest.Pytester):
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

    @pytest.mark.usefixtures("adaptavist")
    def test_default_test_project(self, pytester: pytest.Pytester):
        """Test if a project is set to TEST if not found in markers, testcasename or config."""
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block(1):
                    assert True
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{"test_run_key":"TEST-C1"}')
        hook_record = pytester.inline_run("--adaptavist")
        assert hook_record.matchreport().head_line == "test_T123"

    @pytest.mark.usefixtures("adaptavist")
    def test_skip_no_test_case_methods(self, pytester: pytest.Pytester):
        """Test if a test method which is not a valid adaptavist test case is skipped, if 'skip_ntc_methods' is set"""
        pytester.makepyfile("""
            import pytest

            def test_not_a_test_case(meta_block):
                with meta_block(1):
                    assert True
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{"skip_ntc_methods": true}')
        report = pytester.runpytest("--adaptavist")
        assert report.parseoutcomes()["blocked"] == 1

    def test_early_return_on_no_config(self, pytester: pytest.Pytester, adaptavist: AdaptavistFixture):
        """Test the early return in create_report if config is not valid."""
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block(1):
                    assert True
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{}')
        pytester.runpytest("--adaptavist")
        ctr, etrs, etss = adaptavist
        assert ctr.call_count == 0
        assert etrs.call_count == 0
        assert etss.call_count == 0

    @pytest.mark.xfail(pkg_resources.get_distribution("adaptavist").version == '2.0.0',
                       reason="As long as adaptavist package didn't release the constant fix, this test will fail.")
    def test_skipped_test_cases(self, pytester: pytest.Pytester, adaptavist: AdaptavistFixture):
        """Test that a skipped test case is reported as 'Not Executed'."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.skip()
            def test_T123(meta_block):
                with meta_block(1):
                    assert True
        """)
        with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"index": "0"}]}):
            pytester.runpytest("--adaptavist")
        _, etrs, _ = adaptavist
        assert etrs.call_count == 1
        assert etrs.call_args.kwargs["status"] == "Not Executed"

    def test_test_case_reporting(self, pytester: pytest.Pytester, adaptavist: AdaptavistFixture):
        """Test that a testcase is reported correctly. The steps must not reported in this test."""
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block() as mb:
                    mb.check(True)
        """)
        with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"index": "0"}]}):
            pytester.runpytest("--adaptavist")
            _, etrs, _ = adaptavist
            assert etrs.call_count == 1
            assert etrs.call_args.kwargs["status"] == "Pass"

            pytester.makepyfile("""
                import pytest

                def test_T123(meta_block):
                    with meta_block() as mb:
                        mb.check(False)
            """)
            pytester.runpytest("--adaptavist")
            assert etrs.call_count == 2
            assert etrs.call_args.kwargs["status"] == "Fail"

    @pytest.mark.usefixtures("adaptavist")
    def test_result_attachment(self, pytester: pytest.Pytester):
        """Test that an attachment is correctly attached to the testcase (not to the step)."""
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block() as mb:
                    mb.check(True, attachment="ATTACHMENT", filename="test.txt")
        """)
        with patch("adaptavist.Adaptavist.add_test_result_attachment") as atra:
            pytester.runpytest("--adaptavist")
        assert atra.call_count == 1
        assert atra.call_args.kwargs["attachment"] == "ATTACHMENT"
        assert atra.call_args.kwargs["filename"] == "test.txt"

    def test_skipped_test_cases_keys(self, pytester: pytest.Pytester, adaptavist: AdaptavistFixture):
        """Test that testcases which are not defined in test_case_keys are skipped."""
        pytester.makepyfile("""
            import pytest

            def test_T125(meta_block):
                with meta_block() as mb:
                    mb.check(False)

            def test_T123(meta_block):
                with meta_block() as mb:
                    mb.check(True)
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{"project_key": "TEST", "test_run_key":"TEST-C1", "test_case_keys": ["TEST-T123"]}')
        _, etrs, _ = adaptavist
        outcome = pytester.runpytest("--adaptavist", "-vv").parseoutcomes()
        assert outcome["passed"] == 1
        assert outcome["blocked"] == 1
        assert etrs.call_args.kwargs["test_case_key"] == "TEST-T125"
        assert "skipped as requested" in etrs.call_args.kwargs["comment"]


@pytest.mark.skipif(not system_test_preconditions(), reason="Preconditions for system tests not met. Please see README.md")
class TestPytestAdaptavistSystem:
    """Test connection between pytest and Adaptavist on system test level."""

    def test_T1(self, meta_block: MetaBlockFixture):
        """Test passing a test."""
        with meta_block(1) as mb_1:
            mb_1.check(True)

    @pytest.mark.xfail
    def test_T2(self, meta_block: MetaBlockFixture):
        """Test failing a test."""
        with meta_block(1) as mb_1:
            mb_1.check(False)

    @pytest.mark.xfail
    def test_T3(self, meta_block: MetaBlockFixture):
        """Test reporting steps."""
        with meta_block(1) as mb_1:
            mb_1.check(True)
        with meta_block(2) as mb_2:
            mb_2.check(False)

    def test_T4(self, meta_block: MetaBlockFixture):
        """Test blocking a step."""
        with meta_block(1) as mb_1:
            mb_1.check(True)
        with meta_block(2) as mb_2:
            pytest.block("Testing block")  # type: ignore
            mb_2.check(False)
