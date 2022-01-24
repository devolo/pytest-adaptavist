""" Test Adaptavist test management configuration."""
import os

import pytest
from _pytest.config import ExitCode

from pytest_adaptavist._atm_configuration import ATMConfiguration


def test_get():
    """ Test atm get function. Config dictionary is preferred over OS environment. """
    atm_config = ATMConfiguration()
    atm_config.config["cfg_test_variable"] = "correct source"

    os.environ["cfg_test_variable"] = "wrong source"

    assert atm_config.get("cfg_test_variable") == "correct source"

    atm_config.config["cfg_test"] = "test_cfg"
    assert atm_config.get("test") == "test_cfg"


def test_get_environ():
    """ Test that an OS environment variable is returned if no config is set in dictionary."""
    atm_config = ATMConfiguration()

    os.environ["test_variable"] = "variable from environment"
    assert atm_config.get("test_variable") == "variable from environment"

    os.environ["UPPER_TEST_VARIABLE"] = "upper case variable"
    assert atm_config.get("upper_test_variable") == "upper case variable"


@pytest.mark.parametrize("input_values, output_values",
                         [("true", True), ("1", True), ("yes", True), ("True", True), ("Yes", True), (1, True), (1000, True), ("false", False), ("0", False),
                          ("no", False), ("False", False), ("No", False), (0, False)])
def test_get_bool(input_values, output_values):
    """ Test that the get_bool function return correct boolean values for different input values. It tests strings and integers input."""
    atm_config = ATMConfiguration()
    atm_config.config["test_bool"] = input_values
    assert atm_config.get_bool("test_bool") is output_values


def test_get_bool_exception():
    """ Test that an exception is raised if get_bool can't convert it to a valid boolean value """
    atm_config = ATMConfiguration()
    atm_config.config["test_bool"] = []
    with pytest.raises(ValueError):
        atm_config.get_bool("test_bool")


def test_atm_no_json_file(pytester: pytest.Pytester):
    """ Test if atm configuration will fail if there is no valid json found at ./config/global_config.json"""
    pytester.mkdir("config")
    with open("config/global_config.json", "w", encoding="utf8") as file:
        file.write("This is not valid json")
    report = pytester.runpytest()
    assert report.ret == ExitCode.INTERNAL_ERROR
