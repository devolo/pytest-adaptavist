"""Test connection between pytest and Adaptavist."""

import getpass
import re
from io import BytesIO
from unittest.mock import patch

import pkg_resources
import pytest
from adaptavist import Adaptavist

from . import AdaptavistMock, get_test_values, system_test_preconditions


@pytest.mark.usefixtures("configure")
class TestPytestAdaptavistUnit:
    """Test connection between pytest and Adaptavist on unit test level."""

    @pytest.mark.usefixtures("adaptavist_mock")
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

    @pytest.mark.usefixtures("adaptavist_mock")
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

    @pytest.mark.usefixtures("adaptavist_mock")
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
        assert report.parseoutcomes()["skipped"] == 1

    def test_early_return_on_no_config(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
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
        ctr, etrs, etss = adaptavist_mock
        assert ctr.call_count == 0
        assert etrs.call_count == 0
        assert etss.call_count == 0

    @pytest.mark.xfail(pkg_resources.get_distribution("adaptavist").version == '2.0.0',
                       reason="As long as adaptavist package didn't release the constant fix, this test will fail.")
    def test_skipped_test_cases(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
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
        _, etrs, _ = adaptavist_mock
        assert etrs.call_count == 1
        assert etrs.call_args.kwargs["status"] == "Not Executed"

    def test_test_case_reporting(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test that a testcase is reported correctly. The steps must not reported in this test."""
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block() as mb:
                    mb.check(True)
        """)
        with patch("adaptavist.Adaptavist.get_test_result", return_value={"scriptResults": [{"index": "0"}]}):
            pytester.runpytest("--adaptavist")
            _, etrs, _ = adaptavist_mock
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

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_result_attachment(self, pytester: pytest.Pytester):
        """Test that an attachment is correctly attached to the testcase (not to the step)."""
        pytester.maketxtfile(first_file="foo")
        pytester.makepyfile("""
            import pytest

            def test_T123(meta_block):
                with meta_block() as mb:
                    mb.check(True, attachment="first_file.txt", filename="test.txt")
        """)
        with patch("adaptavist.Adaptavist.add_test_result_attachment") as atra:
            pytester.runpytest("--adaptavist")
        assert atra.call_count == 1
        assert isinstance(atra.call_args.kwargs["attachment"], BytesIO)
        assert atra.call_args.kwargs["filename"] == "test.txt"

    def test_skipped_test_cases_keys(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
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
        _, etrs, _ = adaptavist_mock
        outcome = pytester.runpytest("--adaptavist", "-vv").parseoutcomes()
        assert outcome["passed"] == 1
        assert outcome["skipped"] == 1
        assert etrs.call_args.kwargs["test_case_key"] == "TEST-T123"

    def test_xfail(self, pytester: pytest.Pytester):
        """Test that xfail is handled properly."""
        pytester.makepyfile("""
            import pytest

            @pytest.mark.xfail
            def test_T125(meta_block):
                assert False
        """)
        outcome = pytester.runpytest().parseoutcomes()
        assert outcome["xfailed"] == 1

    def test_correct_stacktrace(self, pytester: pytest.Pytester):
        """Test that the correct stack trace is printed."""
        pytester.makepyfile("""
                def test_a(meta_block):
                    with meta_block(1) as mb_1:
                        mb_1.check(not True)

                def test_b(meta_block):
                    with meta_block(1) as mb_1:
                        mb_1.check(False)
                    with meta_block(2) as mb_2:
                        mb_2.check(not not False)
        """)
        outcome = pytester.runpytest()
        regex = re.findall("not True", str(outcome.outlines).replace('\'', "").replace("[", "").replace("]", ""))
        assert len(regex) == 1
        regex = re.findall("\\(False", str(outcome.outlines).replace('\'', "").replace("[", "").replace("]", ""))
        assert len(regex) == 1
        regex = re.findall("not not False", str(outcome.outlines).replace('\'', "").replace("[", "").replace("]", ""))
        assert len(regex) == 1

    def test_reporting_skipped_test_cases(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Don't report a test case if it is not in test_case_keys."""
        pytester.makepyfile("""
            import pytest

            class TestClass():
                def test_T121(self, meta_block):
                    pass

                def test_T123(self, meta_block):
                    pass
        """)
        with open("config/global_config.json", "w", encoding="utf8") as file:
            file.write('{"test_case_keys": ["TEST-T123"]}')
        _, etrs, _ = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert etrs.call_args_list[0].kwargs["test_case_key"] == "TEST-T123"
        assert etrs.call_count == 1

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_test_run_name(self, pytester: pytest.Pytester):
        """Test that test_run_name template is working."""
        with patch("adaptavist.Adaptavist.create_test_run", return_value="TEST-C123") as ctr, patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={}):
            pytester.makepyfile("""
                import pytest

                class TestClass():
                    def test_T121(self, meta_block):
                        pass

                    def test_T123(self, meta_block):
                        pass
            """)
            with open("config/global_config.json", "w", encoding="utf8") as file:
                file.write('{"jira_server": "https://jira.test", "project_key": "TEST"}')

            pytester.runpytest("--adaptavist")
            assert "TEST test run" in ctr.call_args_list[0][1]['test_run_name']

            pytester.makeini("""
            [pytest]
            test_run_name = Change test_run_name %(project_key)
            """)
            pytester.runpytest("--adaptavist")
            assert ctr.call_args[1]["test_run_name"] == "Change test_run_name TEST"

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_test_plan_name_template(self, pytester: pytest.Pytester):
        """Test that test_run_name template is working."""
        with patch("adaptavist.Adaptavist.create_test_plan") as ctp, patch("adaptavist.Adaptavist.get_test_plans", return_value={}):
            pytester.makepyfile("""
                import pytest

                class TestClass():
                    def test_T121(self, meta_block):
                        pass

                    def test_T123(self, meta_block):
                        pass
            """)
            with open("config/global_config.json", "w", encoding="utf8") as file:
                file.write('{"jira_server": "https://jira.test", "project_key": "TEST", "test_plan_suffix": "suffix"}')

            pytester.runpytest("--adaptavist")
            assert "TEST suffix" in ctp.call_args_list[0][1]['test_plan_name']

            pytester.makeini("""
                [pytest]
                test_plan_name = Change test_plan_name %(project_key)
            """)
            pytester.runpytest("--adaptavist")
            assert "Change test_plan_name TEST" == ctp.call_args[1]['test_plan_name']

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_test_run_name_invalid_key(self, pytester: pytest.Pytester):
        """Test that test_run_name template is working."""
        with patch("adaptavist.Adaptavist.create_test_run", return_value="TEST-C123"), patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={}):
            pytester.makepyfile("""
                import pytest

                class TestClass():
                    def test_T121(self, meta_block):
                        pass

                    def test_T123(self, meta_block):
                        pass
            """)
            with open("config/global_config.json", "w", encoding="utf8") as file:
                file.write('{"jira_server": "https://jira.test", "project_key": "TEST"}')
            pytester.makeini("""
                [pytest]
                test_run_name = Change test_run_name %(project_ey)
            """)
            outcome = pytester.runpytest("--adaptavist")
            assert outcome.ret == 6
            assert any("project_ey" in line for line in outcome.outlines)


@pytest.mark.system
@pytest.mark.skipif(not system_test_preconditions(), reason="Preconditions for system tests not met. Please see README.md")
class TestPytestAdaptavistSystem:
    """Test connection between pytest and Adaptavist on system test level."""

    def test_T1(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test passing a test."""
        pytester.makepyfile("""
            def test_T1(meta_block):
                with meta_block():
                    with meta_block(1) as mb_1:
                        mb_1.check(True)
        """)
        pytester.makeini(f"""
            [pytest]
            restrict_user = {getpass.getuser().lower()}
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Pass"
        assert test_result["scriptResults"][0]["status"] == "Pass"

    def test_T2(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test failing a test."""
        pytester.makepyfile("""
            def test_T2(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Fail"
        assert test_result["scriptResults"][0]["status"] == "Fail"

    def test_T3(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test reporting steps."""
        pytester.makepyfile("""
            def test_T3(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
                with meta_block(2) as mb_2:
                    mb_2.check(False)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Fail"
        assert test_result["scriptResults"][0]["status"] == "Pass"
        assert test_result["scriptResults"][1]["status"] == "Fail"

    def test_T4(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test blocking a step."""
        pytester.makepyfile("""
            import pytest

            def test_T4(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
                with meta_block(2) as mb_2:
                    pytest.block("Testing block")  # type: ignore
                    mb_2.check(False)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Blocked"
        assert test_result["comment"] == "Testing block<br>Step 2 blocked"
        assert test_result["scriptResults"][0]["status"] == "Pass"
        assert test_result["scriptResults"][1]["status"] == "Blocked"

    def test_T6(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test skipping a step."""
        pytester.makepyfile("""
            import pytest

            def test_T6(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
                with meta_block(2) as mb_2:
                    pytest.skip("Testing skip")
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "In Progress"
        assert test_result["scriptResults"][0]["status"] == "Pass"
        assert test_result["scriptResults"][1]["status"] == "Not Executed"

    def test_T7(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test comments."""
        pytester.makepyfile("""
            def test_T7(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, message_on_pass="testing pass comment")
                with meta_block(2) as mb_2:
                    mb_2.check(False, message_on_fail="testing fail comment")
                with meta_block(3) as mb_3:
                    raise ValueError("testing exception reporting")
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert test_result["status"] == "Fail"
        assert test_result["scriptResults"][0]["status"] == "Pass"
        assert "testing pass comment" in test_result["scriptResults"][0]["comment"]
        assert test_result["scriptResults"][1]["status"] == "Fail"
        assert "testing fail comment" in test_result["scriptResults"][1]["comment"]
        assert test_result["scriptResults"][2]["status"] == "Fail"
        assert "testing exception reporting" in test_result["scriptResults"][2]["comment"]

    def test_T8(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """Test attachments."""
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T8(meta_block):
                with open("first_file.txt", "rb") as f:
                    with meta_block() as mb:
                        f.seek(1)
                        mb.check(True, attachment=f)
                        mb.check(True, attachment="second_file.txt")
                with meta_block(1) as mb_1:
                    with open("first_file.txt", "rb") as f:
                        mb_1.check(True, attachment=f)
                        mb_1.check(True, attachment="second_file.txt")
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        test_result = adaptavist.get_test_result_attachment(test_run_key, test_name)
        assert len(test_result) == 4
        assert test_result[0]["filename"] == "second_file.txt"
        assert test_result[0]["filesize"] == 3
        assert test_result[1]["filename"] == "first_file.txt"
        assert test_result[1]["filesize"] == 2
        assert test_result[2]["filename"] == "second_file.txt"
        assert test_result[2]["filesize"] == 3
        assert test_result[3]["filename"] == "first_file.txt"
        assert test_result[3]["filesize"] == 3

    def test_T9(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """
        Test meta_block.Action.FAIL_CONTEXT.
        Expect that step 1 fails, attachment on step 1 and step 2 passes.
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T9(meta_block):
                with meta_block() as mb:
                    mb.check(True)
                with meta_block(1) as mb_1:
                    mb_1.check(False)
                    mb_1.check(True, attachment="second_file.txt")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        attachments = adaptavist.get_test_result_attachment(test_run_key, test_name)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert len(attachments) == 1
        assert test_result["status"] == "Fail"
        assert test_result["scriptResults"][0]["status"] == "Fail"
        assert test_result["scriptResults"][1]["status"] == "Pass"

    def test_T10(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """
        Test meta_block.Action.STOP_CONTEXT.
        Expect that step 1 is blocked, step 2 passes and overall test result is blocked.
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T10(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_CONTEXT)
                    mb_1.check(True, attachment="second_file.txt")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        attachments = adaptavist.get_test_result_attachment(test_run_key, test_name)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert len(attachments) == 0
        assert test_result["status"] == "Blocked"
        assert test_result["comment"] == "Step 1 blocked"
        assert test_result["scriptResults"][0]["status"] == "Blocked"
        assert test_result["scriptResults"][1]["status"] == "Pass"

    def test_T11(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """
        Test meta_block.Action.FAIL_METHOD.
        Expect that step 1 is failed, no attachment at step 1, step 2 not executed and overall test result is failed.
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T11(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.FAIL_METHOD)
                    mb_1.check(True, attachment="second_file.txt")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        attachments = adaptavist.get_test_result_attachment(test_run_key, test_name)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert len(attachments) == 0
        assert test_result["status"] == "Fail"
        assert test_result["comment"] == "Step 1 failed:"
        assert test_result["scriptResults"][0]["status"] == "Fail"
        assert test_result["scriptResults"][1]["status"] == "Not Executed"

    def test_T12(self, pytester: pytest.Pytester, adaptavist: Adaptavist):
        """
        Test meta_block.Action.STOP_METHOD.
        Expect that step 1 is blocked, no attachment at step 1, step 2 not executed and overall test result is blocked.
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T12(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_METHOD)
                    mb_1.check(True, attachment="second_file.txt")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        test_run_key, test_name = get_test_values(report)
        attachments = adaptavist.get_test_result_attachment(test_run_key, test_name)
        test_result = adaptavist.get_test_result(test_run_key, test_name)
        assert len(attachments) == 0
        assert test_result["status"] == "Blocked"
        assert test_result["scriptResults"][0]["status"] == "Blocked"
        assert test_result["scriptResults"][1]["status"] == "Not Executed"

    def test_T13(self, pytester: pytest.Pytester, adaptavist: Adaptavist, test_run: str):
        """
        Test meta_block.Action.FAIL_SESSION.
        Expect that T13 is failed, no attachment at T13, T12 is set to blocked. T11 is untouched and status In Progress
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T11(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
            def test_T13(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.FAIL_SESSION)
                    mb_1.check(True, attachment="second_file.txt")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
            def test_T12(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        _, test_name = get_test_values(report, "test_T13")
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "Fail"
        _, test_name = get_test_values(report, "test_T12")
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "Blocked"
        _, test_name = get_test_values(report, "test_T11")
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "In Progress"  # Ensure that T11 is untouched

    def test_T14(self, pytester: pytest.Pytester, adaptavist: Adaptavist, test_run: str):
        """
        Test meta_block.Action.STOP_SESSION.
        Expect that T14 is blocked, step 2 not executed. T12 also set to blocked
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T14(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_SESSION)
                with meta_block(2) as mb_2:
                    mb_2.check(True)
            def test_T12(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        report = pytester.inline_run("--adaptavist")
        _, test_name = get_test_values(report, "test_T14")
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "Blocked"
        _, test_name = get_test_values(report, "test_T12")
        assert test_result["status"] == "Blocked"

    def test_T15(self, pytester: pytest.Pytester, adaptavist: Adaptavist, test_run: str):
        """
        Test meta_block.Action.STOP_EXIT_SESSION.
        Expect that T15 is blocked. T12 not in test result --> not in test cycle in ATM
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            def test_T15(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_EXIT_SESSION)
                with meta_block(2) as mb_2:
                    mb_2.check(True)
            def test_T12(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        pytester.inline_run("--adaptavist")
        test_name = test_run.split("-")[0] + "-T15"
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "Blocked"
        test_name = test_run.split("-")[0] + "-T12"
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result == {}

    def test_T16(self, pytester: pytest.Pytester, adaptavist: Adaptavist, test_run: str):
        """
        Test meta_data
        Expect that T16 is failed. Upload file with correct filename and size.
        """
        pytester.maketxtfile(first_file="foo")
        pytester.maketxtfile(second_file="bar")
        pytester.makepyfile("""
            import io
            def test_T16(meta_data):
                meta_data["comment"] = "unexpected result"
                attachment = io.StringIO()
                attachment.write("this is just a simple attachment")
                meta_data["attachment"] = attachment
                meta_data["filename"] = "content.txt"
                assert False
        """)
        pytester.inline_run("--adaptavist")
        test_name = test_run.split("-")[0] + "-T16"
        test_result = adaptavist.get_test_result(test_run, test_name)
        assert test_result["status"] == "Fail"
        attachments = adaptavist.get_test_result_attachment(test_run, test_name)
        assert attachments[0]["filename"] == "content.txt"
        assert attachments[0]["filesize"] == 32
