import logging
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("marker", ["mark.block", "mark.project", "mark.testcase"])
def test_adaptavist_markers(pytester, marker):
    result = pytester.runpytest("--markers")
    assert any(marker in line for line in result.stdout.lines)


def test_adaptavist_disabled(pytester):
    pytester.makepyfile("""
        def test_hello_default():
            assert True
    """)
    result = pytester.runpytest()
    assert all("reporting: enabled" not in line for line in result.stdout.lines)


def test_adaptavist_enabled(pytester):
    pytester.makepyfile("""
        def test_hello_default():
            assert True
    """)
    config = pytester.parseconfig("--adaptavist")
    assert config.option.adaptavist


def test_adaptavist_enabled_ini_file(pytester):
    pytester.makepyfile("""
        def test_hello_default():
            assert True
    """)
    pytester.makeini("""
        [pytest]
        adaptavist = 1
        """)
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        result = pytester.runpytest()
    assert any("reporting: enabled" in line for line in result.stdout.lines)


def test_blocked_testcase(pytester):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.block()
        def test_hello_default():
            assert True
    """)
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        result = pytester.runpytest()
    assert result.parseoutcomes()["blocked"] == 1


def test_blocked_during_runtime(pytester):
    pytester.makepyfile("""
        import pytest
        def test_hello_default():
            pytest.block()
            assert True
    """)
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        result = pytester.runpytest()
    assert result.parseoutcomes()["blocked"] == 1


def test_xdist_handling(pytester):
    fixtures = ["items"]
    pytester.makepyfile("""
        import pytest
        def test_hello_default():
            assert True
    """)
    with patch("pytest_adaptavist.atm_user_is_valid", return_value=True):
        result = pytester.runpytest("--adaptavist")
    assert any("reporting: enabled" in line for line in result.stdout.lines)


def test_adaptavist_call(pytester):
    import os
    pytester.makepyfile("""
        import pytest
        @pytest.mark.project("test")
        def test_TEST_T123():
            assert True
    """)
    pytester.mkdir("config")
    os.chdir("config")
    with open("global_config.json", "w") as f:
        f.write('{"project_key": "TEST", "test_run_key":"TEST-C1"}')
    os.environ["JIRA_SERVER"] = "https://test.com"
    pytester.chdir()
    r_value = [{"key": "TEST-T123"}]
    with patch("adaptavist.Adaptavist.get_test_result", return_value={}):
        with patch("adaptavist.Adaptavist.get_test_run", return_value={"items": [{"testCaseKey": "TEST-T123"}]}):
            with patch("adaptavist.Adaptavist.get_test_cases", return_value=r_value):
                with patch("adaptavist.Adaptavist.get_test_run_by_name", return_value={"key": "TEST_RUN_TEST"}):
                    with patch("requests.post") as mock_post, patch("pytest_adaptavist.atm_user_is_valid", return_value=True), patch("requests.put") as mock_put:
                        with patch("adaptavist.Adaptavist.get_test_case", return_value={"name": "TEST-T123", "priority": "Normal"}):
                            with patch("adaptavist.Adaptavist.create_test_result") as ctr:
                                pytester.runpytest("--adaptavist")
                                ctr.assert_called_once_with(test_run_key="TEST-C1", test_case_key="TEST-T123", environment="", status=None)
                                # data= {"comment": "", "environment": None, "assignedTo": "markus.bong", "exectedBy": "markus.bong", "status": None})


# @pytest.mark.block()
# def test_TEST_T970(meta_block):
#         with meta_block() as mb:
#             """Precondition"""
#             with meta_block(1) as mb_1:
#                 """
#                 Step:
#                 Open https://stage.devolo.scalecommerce.cloud/produkte

#                 Expected result:
#                 https://stage.devolo.scalecommerce.cloud/produkte is open.

#                 """
#                 a = "String"
#                 b = 2
#                 c = b
#                 mb_1.check(False, message_on_fail="MESSAGE_ON_FAIL")

#             with meta_block(2) as mb_2:
#                 """
#                 Step:
#                 Search for devolo Magic 2 WiFi next Starterkit (Artikel-Nr.: 08614) and click "In den Warenkorb" Button

#                 Expected result:
#                 The Shopping Cart Overlay opens and informs the user about the addition to the shopping cart.

#                 """
#                 mb_2.check(True, message_on_fail="MESSAGE_ON_FAIL")
#                 # Get class for Wifi next starterkit
#             logger = logging.getLogger(__name__)
#             logger.debug("Debug")
#             logger.info("INFODHASLAÖLSLASJALSKASAKSLAKLS")
#             # mb.check(False)

# # @pytest.mark.parametrize("v", ["a", "b"])
# class TestA:

#     def test_TEST_T968(self, meta_block):
#         with meta_block() as mb:
#             """Precondition"""
#             with meta_block(1) as mb_1:
#                 """
#                 Step:
#                 Open https://stage.devolo.scalecommerce.cloud/produkte

#                 Expected result:
#                 https://stage.devolo.scalecommerce.cloud/produkte is open.

#                 """
#                 a = "String"
#                 b = 2
#                 c = b
#                 # pytest.assume(False, "MESSAGE")
#                 mb_1.check(False, message_on_fail="MESSAGE_ON_FAIL")

#             with meta_block(2) as mb_2:
#                 """
#                 Step:
#                 Search for devolo Magic 2 WiFi next Starterkit (Artikel-Nr.: 08614) and click "In den Warenkorb" Button

#                 Expected result:
#                 The Shopping Cart Overlay opens and informs the user about the addition to the shopping cart.

#                 """
#                 mb_2.check(True, message_on_fail="MESSAGE_ON_FAIL")
#                 # Get class for Wifi next starterkit
#             logger = logging.getLogger(__name__)
#             logger.debug("Debug")
#             logger.info("INFODHASLAÖLSLASJALSKASAKSLAKLS")
#             # mb.check(False)

# #     @pytest.mark.block()
# #     def test_TEST_T969(self, meta_block):
# #         """
# #         [summary]

# #         :param meta_block: [description]
# #         :type meta_block: [type]
# #         """
# #         with meta_block() as mb:
# #             """Precondition"""
# #             with meta_block(1) as mb_1:
# #                 """
# #                 Step:
# #                 Open https://stage.devolo.scalecommerce.cloud/produkte

# #                 Expected result:
# #                 https://stage.devolo.scalecommerce.cloud/produkte is open.

# #                 """
# #                 a = "String"
# #                 b = 2
# #                 c = b
# #                 # pytest.assume(False, "MESSAGE")
# #                 mb_1.check(True, message_on_fail="MESSAGE_ON_FAIL")

# #             with meta_block(2) as mb_2:
# #                 """
# #                 Step:
# #                 Search for devolo Magic 2 WiFi next Starterkit (Artikel-Nr.: 08614) and click "In den Warenkorb" Button

# #                 Expected result:
# #                 The Shopping Cart Overlay opens and informs the user about the addition to the shopping cart.

# #                 """

# #                 # Get class for Wifi next starterkit
# #             logger = logging.getLogger(__name__)
# #             logger.debug("Debug")
# #             logger.info("INFODHASLAÖLSL")
# #             # mb.check(False)
