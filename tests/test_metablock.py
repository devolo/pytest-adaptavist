import os
from unittest.mock import patch

import pytest


def test_message_on_fail(pytester, adaptavist):
    """Test the correct usage of the message_on_fail parameter of meta_block check."""
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, message_on_fail="We want to see this message")
    """)
    _, _, etss = adaptavist
    pytester.runpytest("--adaptavist")
    assert "We want to see this message" in etss.call_args.kwargs["comment"]

    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True, message_on_fail="We don't want to see this message")
    """)
    pytester.runpytest("--adaptavist")
    assert "We don't want to see this message" not in etss.call_args.kwargs["comment"]


def test_message_on_pass(pytester, adaptavist):
    """Test the correct usage of the message_on_pass parameter of meta_block check."""
    # Test if the message_on_pass is given to the adaptavist call.
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True, message_on_pass="We want to see this message")
    """)
    _, _, etss = adaptavist
    pytester.runpytest("--adaptavist")
    assert "We want to see this message" in etss.call_args.kwargs["comment"]

    # Test if the message_on_pass is not given to adaptavist call on failure.
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, message_on_pass="We don't want to see this message")
    """)
    pytester.runpytest("--adaptavist")
    assert "We don't want to see this message" not in etss.call_args.kwargs["comment"]


def test_description(pytester, adaptavist):
    """Test the correct usage of the description parameter of meta_block check."""
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True, description="This should be displayed twice")
                mb_1.check(False, description="This should be displayed twice")
    """)
    _, _, etss = adaptavist
    pytester.runpytest("--adaptavist")
    assert etss.call_args.kwargs["comment"].count("This should be displayed twice") == 2


def test_attachment(pytester, adaptavist):
    """Test the correct usage of the attachment parameter."""

    # Positive case
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True, attachment="This is an attachment")
    """)
    with patch("adaptavist.Adaptavist.add_test_script_attachment") as atsa:
        pytester.runpytest("--adaptavist")
        assert "This is an attachment" in atsa.call_args.kwargs["attachment"]

    # Negative case
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, attachment="This is an attachment")
    """)
    with patch("adaptavist.Adaptavist.add_test_script_attachment") as atsa:
        pytester.runpytest("--adaptavist")
        assert "This is an attachment" in atsa.call_args.kwargs["attachment"]


def test_description_of_test_steps_printed(pytester, adaptavist):
    """Test if the 'docstring' of testcases is printed if pytest is started with at least verbosity == 2."""

    # Positive case
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                \"\"\"Description of test step 1\"\"\"
                mb_1.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert "Description of test step 1" in report.outlines

    # Negative case
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                \"\"\"Description of test step 1\"\"\"
                mb_1.check(True)
    """)
    report = pytester.runpytest("--adaptavist")
    assert "Description of test step 1" not in report.outlines


def test_adaptavist_call_metablock(pytester, adaptavist):
    """Test if every meta_block is reported to adaptavist."""
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1):
                assert True
            with meta_block(2):
                assert True
            with meta_block(3):
                assert False
    """)
    _, etrs, _ = adaptavist
    pytester.runpytest("--adaptavist")
    assert etrs.call_count == 4


def test_meta_block_timeout(pytester, adaptavist):
    """Test if a meta_block is stopped if the timeout is reached."""
    pytester.makepyfile("""
        import pytest
        from time import sleep
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1, 1):
                sleep(2)
                assert True
    """)
    report = pytester.runpytest("--adaptavist")
    assert report.parseoutcomes()["skipped"] == 1


def test_meta_block_check_unknown_arguments(pytester, adaptavist):
    """Test if meta_block handles unknown keyword arguments correctly."""
    pytester.makepyfile("""
        import pytest
        from time import sleep
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True, unknown_kwargs=123)
    """)
    report = pytester.runpytest("--adaptavist")
    assert any(("Unknown arguments: {'unknown_kwargs': 123}" in x for x in report.outlines))


def test_meta_block_assume(pytester, adaptavist):
    """Test if meta_block is using assume correctly. We expect that Step 2 is executed even if Step 1 fails."""
    pytester.makepyfile("""
        import pytest
        from time import sleep
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False)
            with meta_block(2) as mb_2:
                mb_2.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert any("Step 2" in x for x in report.outlines)


def test_meta_block_assert(pytester, adaptavist):
    """Test Action.FAIL_METHOD. We expect that Step 2 is not executed as Step 1 will fail."""
    pytester.makepyfile("""
        import pytest
        from time import sleep
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.FAIL_METHOD)
            with meta_block(2) as mb_2:
                mb_2.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert all("Step 2" not in x for x in report.outlines)


def test_meta_block_stop_context(pytester, adaptavist):
    """Test Action.STOP_CONTEXT. We expect that the second check in meta_block 1 is not executed, but Step 2 must be executed."""
    pytester.makepyfile("""
        import pytest
        from time import sleep
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.STOP_CONTEXT)
                mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
            with meta_block(2) as mb_2:
                mb_2.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert all("THIS SHOULD NOT BE DISPLAYED" not in x for x in report.outlines)
    assert any("Step 2" in x for x in report.outlines)


def test_meta_block_stop_method(pytester, adaptavist):
    """Test Action.STOP_METHOD. We expect to not see Step 2 and the second check of meta_block 1. TEST-T124 must be executed normally."""
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.STOP_METHOD)
                mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
            with meta_block(2) as mb_2:
                mb_2.check(True)

        @pytest.mark.project("test")
        def test_TEST_T124(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert all("THIS SHOULD NOT BE DISPLAYED" not in x for x in report.outlines)
    assert any("Step 2" not in x for x in report.outlines)
    assert any("test_TEST_T124 PASSED" in x for x in report.outlines)


def test_meta_block_check_stop_session(pytester, adaptavist):
    """Test Action.STOP_SESSION. We expect that TEST_T121 is executed. TEST_T123 fails and prevent execution of TEST_T124"""
    pytester.makepyfile("""
        import pytest
        from time import sleep

        @pytest.mark.project("test")
        def test_TEST_T121(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True)

        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.STOP_SESSION)

        @pytest.mark.project("test")
        def test_TEST_T124(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True)  # This should not be executed because of the STOP_SESSION
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    outcome = report.parseoutcomes()
    assert outcome["passed"] == 1
    assert outcome["skipped"] == 1
    assert outcome["blocked"] == 1
    # TODO: It seems like the Test are sorted differently. Maybe of the config fixture. That results in not getting the expecting result.


def test_meta_block_check_fail_session(pytester, adaptavist):
    pytester.makepyfile("""
        import pytest
        from time import sleep

        @pytest.mark.project("test")
        def test_TEST_T121(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True)

        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.FAIL_SESSION)

        @pytest.mark.project("test")
        def test_TEST_T124(meta_block):
            with meta_block(1):
                assert True  # This should not be executed because of the FAIL_SESSION
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    outcome = report.parseoutcomes()
    assert outcome["passed"] == 1
    assert outcome["failed"] == 1
    assert outcome["blocked"] == 1
    # TODO: It seems like the Test are sorted differently. Maybe of the config fixture. That results in not getting the expecting result.


def test_meta_block_exit_session(pytester, adaptavist):
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(False, action_on_fail=mb_1.Action.EXIT_SESSION)
                mb_1.check(False, message_on_fail="THIS SHOULD NOT BE DISPLAYED")
            with meta_block(2) as mb_2:
                mb_2.check(True)

        @pytest.mark.project("test")
        def test_TEST_T124(meta_block):
            with meta_block(1) as mb_1:
                mb_1.check(True)
    """)
    report = pytester.runpytest("--adaptavist", "-vv")
    assert all("THIS SHOULD NOT BE DISPLAYED" not in x for x in report.outlines)
    assert any("Step 2" not in x for x in report.outlines)
    assert all("test_TEST_T124" not in x for x in report.outlines)
    assert report.parseoutcomes().get("passed") is None
