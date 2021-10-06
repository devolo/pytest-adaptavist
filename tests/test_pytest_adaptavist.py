from unittest.mock import patch


def test_default_test_project(pytester, adaptavist):
    """Test if a project is set to TEST if not found in markers, testcasename or config"""
    pytester.makepyfile("""
        import pytest
        def test_T123(meta_block):
            with meta_block(1):
                assert True
    """)
    with open("config/global_config.json", "w") as f:
        f.write('{"test_run_key":"TEST-C1"}')
    hook_record = pytester.inline_run("--adaptavist")
    plugin = hook_record._pluginmanager.getplugin("_adaptavist")
    assert plugin.test_refresh_info.get("TEST-T123") is not None


def test_skip_no_test_case_methods(pytester, adaptavist):
    """Test if a test method which is not a valid adaptavist test case is skipped, if 'skip_ntc_methods' is set"""
    pytester.makepyfile("""
        import pytest
        def test_not_a_test_case(meta_block):
            with meta_block(1):
                assert True
    """)
    with open("config/global_config.json", "w") as f:
        f.write('{"skip_ntc_methods": true}')
    report = pytester.runpytest("--adaptavist", "-vv")
    assert report.parseoutcomes()["blocked"] == 1


# def test_early_return_on_no_config(pytester, adaptavist):
#     """Test the early return in pytest_collection_modifyitems if config can not be loaded."""
#     pytester.makepyfile("""
#         import pytest
#         def test_not_a_test_case(meta_block):
#             with meta_block(1):
#                 assert True
#     """)
#     with open("config/global_config.json", "w") as f:
#         f.write('{}')
#     with patch("pytest_adaptavist._pytest_adaptavist.PytestAdaptavist.atm_configure", return_value=False):
#         report = pytester.inline_run("--adaptavist", "-vv")
#         # TODO: Find a meaningful assert
