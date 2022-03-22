"""Test meta block functionality."""

from unittest.mock import patch

import pytest

from . import AdaptavistMock


@pytest.mark.usefixtures("configure")
class TestMetaBlockUnit:
    """Test meta block functionality on unit test level."""

    def test_message_on_fail(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test the correct usage of the message_on_fail parameter of meta_block check."""

        # Test message_on_fail for a failing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, message_on_fail="We want to see this message")
        """)
        _, _, etss = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert "We want to see this message" in etss.call_args.kwargs["comment"]

        # Test message_on_fail for a passing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, message_on_fail="We don't want to see this message")
        """)
        pytester.runpytest("--adaptavist")
        assert "We don't want to see this message" not in etss.call_args.kwargs["comment"]

    def test_message_on_pass(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test the correct usage of the message_on_pass parameter of meta_block check."""

        # Test message_on_pass for a passing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, message_on_pass="We want to see this message")
        """)
        _, _, etss = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert "We want to see this message" in etss.call_args.kwargs["comment"]

        # Test message_on_pass for a failing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, message_on_pass="We don't want to see this message")
        """)
        pytester.runpytest("--adaptavist")
        assert "We don't want to see this message" not in etss.call_args.kwargs["comment"]

    def test_description(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test the correct usage of the description parameter of meta_block check."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, description="This should be displayed twice")
                    mb_1.check(False, description="This should be displayed twice")
        """)
        _, _, etss = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert etss.call_args.kwargs["comment"].count("This should be displayed twice") == 2

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_attachment(self, pytester: pytest.Pytester):
        """Test the correct usage of the attachment parameter."""
        pytester.maketxtfile(first_file="foo")

        # Test attachment for a passing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, attachment="first_file.txt")
        """)
        with patch("adaptavist.Adaptavist.add_test_script_attachment") as atsa:
            pytester.runpytest("--adaptavist")
            assert "first_file.txt" in atsa.call_args.kwargs["filename"]

        # Test attachment for a failing test case
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, attachment="first_file.txt")
        """)
        with patch("adaptavist.Adaptavist.add_test_script_attachment") as atsa:
            pytester.runpytest("--adaptavist")
            assert "first_file.txt" in atsa.call_args.kwargs["filename"]

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_description_of_test_steps_printed(self, pytester: pytest.Pytester):
        """Test if the description of testcases is printed, if pytest is started with high verbosity."""
        pytester.makepyfile('''
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    """Description of test step 1"""
                    mb_1.check(True)
        ''')

        # Low verbosity
        report = pytester.runpytest("--adaptavist")
        assert "Description of test step 1" not in report.outlines

        # High verbosity
        report = pytester.runpytest("--adaptavist", "-vv")
        assert "Description of test step 1" in report.outlines

    def test_adaptavist_call_metablock(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test if all meta blocks are reported to adaptavist."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1):
                    assert True
                with meta_block(2):
                    assert True
                with meta_block(3):
                    assert False
        """)
        _, etrs, _ = adaptavist_mock
        pytester.runpytest("--adaptavist")
        assert etrs.call_count == 4  # 3 meta blocks and 1 overall result

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_meta_block_timeout(self, pytester: pytest.Pytester):
        """Test if a meta block is timed out."""
        pytester.makepyfile("""
            from time import sleep
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1, 1):
                    sleep(2)
                    assert True
        """)
        outcome = pytester.runpytest("--adaptavist").parseoutcomes()
        assert outcome["skipped"] == 1

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_meta_block_timeout_fail(self, pytester: pytest.Pytester):
        """Test if a meta block is timed out with fail action."""
        pytester.makepyfile("""
            from time import sleep
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1, timeout=1, action_on_timeout=0):
                    sleep(2)
                    assert True
        """)
        outcome = pytester.runpytest("--adaptavist").parseoutcomes()
        assert outcome["failed"] == 1

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_meta_block_check_unknown_arguments(self, pytester: pytest.Pytester):
        """Test if meta_block handles unknown keyword arguments correctly."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True, unknown_kwargs=123)
        """)
        report = pytester.runpytest("--adaptavist")
        assert any(("Unknown arguments: {'unknown_kwargs': 123}" in x for x in report.outlines))

    def test_meta_block_assume(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test if meta_block is using assume correctly. Step 2 must be executed even if step 1 fails."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False)
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        pytester.runpytest("--adaptavist")
        _, _, etss = adaptavist_mock
        assert etss.call_count == 2

    def test_meta_block_fail_method(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test Action.FAIL_METHOD. Step 2 must not be executed as step 1 will fail."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.FAIL_METHOD)
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        pytester.runpytest("--adaptavist")
        _, _, etss = adaptavist_mock
        assert etss.call_count == 1

    def test_meta_block_stop_context(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test Action.STOP_CONTEXT. The second check in meta_block 1 must not be executed, but step 2 must be executed."""

        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_CONTEXT)
                    mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
                with meta_block(2) as mb_2:
                    mb_2.check(True)
        """)
        report = pytester.runpytest("--adaptavist", "-vv")
        _, _, etss = adaptavist_mock
        for call in etss.call_args_list:
            assert "THIS SHOULD NOT BE DISPLAYED" not in call.kwargs["comment"]
        assert etss.call_count == 2
        assert etss.call_args.kwargs["step"] == 2
        assert etss.call_args.kwargs["status"] == "Pass"
        assert report.parseoutcomes()["skipped"] == 1

    def test_meta_block_stop_method(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test Action.STOP_METHOD. We expect to not see step 2 and the second check of meta_block 1. TEST-T124 must be executed normally."""

        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_METHOD)
                    mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
                with meta_block(2) as mb_2:
                    mb_2.check(True)

            def test_TEST_T124(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        pytester.runpytest("--adaptavist")
        _, _, etss = adaptavist_mock
        assert etss.call_count == 2
        for call in etss.call_args_list:
            assert "THIS SHOULD NOT BE DISPLAYED" not in call.kwargs["comment"]
            assert call.test_case_key != "TEST-T123" or call.step != 2

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_meta_block_check_stop_session(self, pytester: pytest.Pytester):
        """Test Action.STOP_SESSION. We expect that TEST_T121 is executed. TEST_T123 fails and prevent execution of TEST_T124"""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T121(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_SESSION)

            def test_TEST_T124(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        outcome = pytester.runpytest("--adaptavist").parseoutcomes()
        assert outcome["passed"] == 1
        assert outcome["blocked"] == 2

    @pytest.mark.usefixtures("adaptavist_mock")
    def test_meta_block_check_fail_session(self, pytester: pytest.Pytester):
        """Test Action.FAIL_SESSION. We expect that TEST_T121 is executed. TEST_T123 fails and fails the whole session."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T121(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.FAIL_SESSION)

            def test_TEST_T124(meta_block):
                with meta_block(1):
                    assert True
        """)
        outcome = pytester.runpytest("--adaptavist").parseoutcomes()
        assert outcome["failed"] == 1
        assert outcome["blocked"] == 1
        assert outcome["passed"] == 1

        test_runs = {"items": [{"testCaseKey": "TEST-T123"}, {"testCaseKey": "TEST-T124"}, {"testCaseKey": "TEST-T121"}]}
        with patch("adaptavist.Adaptavist.get_test_run", return_value=test_runs):
            outcome = pytester.runpytest("--adaptavist").parseoutcomes()
            assert outcome["failed"] == 1
            assert outcome["blocked"] == 2

    def test_meta_block_stop_exit_session(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test Action.EXIT_SESSION. We expect that TEST_T123 fails and exits the whole session."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.STOP_EXIT_SESSION)
                    mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
                with meta_block(2) as mb_2:
                    mb_2.check(True)

            def test_TEST_T124(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        pytester.runpytest("--adaptavist")
        _, _, etss = adaptavist_mock
        assert etss.call_count == 1
        assert etss.call_args.kwargs["status"] == "Blocked"

    def test_meta_block_fail_exit_session(self, pytester: pytest.Pytester, adaptavist_mock: AdaptavistMock):
        """Test Action.EXIT_SESSION. We expect that TEST_T123 fails and exits the whole session."""
        pytester.makepyfile("""
            import pytest

            def test_TEST_T123(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(False, action_on_fail=mb_1.Action.FAIL_EXIT_SESSION)
                    mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
                with meta_block(2) as mb_2:
                    mb_2.check(True)

            def test_TEST_T124(meta_block):
                with meta_block(1) as mb_1:
                    mb_1.check(True)
        """)
        pytester.runpytest("--adaptavist")
        _, _, etss = adaptavist_mock
        assert etss.call_count == 1
        assert etss.call_args.kwargs["status"] == "Fail"
