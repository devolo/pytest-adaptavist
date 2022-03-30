"""This module provides a set of pytest hooks for generating Adaptavist test run results from test reports."""

from __future__ import annotations

import getpass
import logging
import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal, NoReturn

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.outcomes import Skipped, _with_exception
from _pytest.reports import TestReport

from ._atm_configuration import atm_user_is_valid
from ._helpers import get_code_base_url, get_option_ini
from ._pytest_adaptavist import PytestAdaptavist
from ._xdist import XdistHooks
from .constants import META_BLOCK_TIMEOUT, TEST_PLAN_NAME_DEFAULT, TEST_RUN_NAME_DEFAULT
from .metablock import MetaBlock
from .types import MetaBlockFixture, MetaDataFixture

__all__ = ["PytestAdaptavist", "MetaBlock", "MetaBlockFixture", "MetaDataFixture"]
try:
    __version__ = version("adaptavist")
except PackageNotFoundError:
    # package is not installed - e.g. pulled and run locally
    __version__ = "0.0.0"


def pytest_addoption(parser: Parser):
    """Add options to control plugin."""
    group = parser.getgroup("adaptavist", "adaptavist test reporting")

    def add_option_ini(option: str, dest: str, default: str | None = None, option_type: Literal['bool'] | None = None, **kwargs: Any):
        group.addoption(option, dest=dest, **kwargs)
        kwargs.pop("store", "")
        parser.addini(dest, default=default, type=option_type, help="default value for " + option)

    add_option_ini("--adaptavist", dest="adaptavist", option_type="bool", action="store_true", help="Enable adaptavist reporting (default: False).")
    add_option_ini("--restrict-user", dest="restrict_user", help="Only send data to Adaptavist, if this user is executing the tests.")
    add_option_ini("--restrict-branch",
                   dest="restrict_branch",
                   action="store_true",
                   option_type="bool",
                   help="Only send data to Adaptavist, if a certain branch is used.")
    add_option_ini("--restrict-branch-name", dest="restrict_branch_name", default="origin/master", help="Branch to restrict to (default: origin/master)")
    add_option_ini("--test_run_name", dest="test_run_name", default=TEST_RUN_NAME_DEFAULT)
    add_option_ini("--test_plan_name", dest="test_plan_name", default=TEST_PLAN_NAME_DEFAULT)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config):
    """Configure reporting to Adaptavist and introduce pytest.block."""

    # Register custom markers
    config.addinivalue_line("markers", "testcase: mark test method as test case implementation (for internal use only)")
    config.addinivalue_line("markers", "project(project_key): mark test method to be related to given project (used to create appropriate test case key")
    config.addinivalue_line("markers", "block(reason): mark test method to be blocked")
    config.addinivalue_line("markers", "blockif(condition, ..., *, reason=...): mark test method to be blocked if any of the conditions evaluate to True")

    adaptavist = PytestAdaptavist(config)
    config.pluginmanager.register(adaptavist, "_adaptavist")

    # Support for pytest.block
    @_with_exception(Blocked)
    def block(msg="") -> NoReturn:
        __tracebackhide__ = True  # pylint: disable=unused-variable
        raise Blocked(msg=msg)

    pytest.block = block  # type: ignore

    # Stop here, if pytest_adaptavist is not activated
    if not get_option_ini(config, "adaptavist"):
        return

    # Configure xdist nodes, if pytest_xdist is installed
    if config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(XdistHooks(), "_xdist_adaptavist")

    # Check, if user is known in Adaptavist
    build_usr = getpass.getuser().lower()
    if get_option_ini(config, "restrict_user") and get_option_ini(config, "restrict_user") != build_usr:
        adaptavist.enabled = False
    if not atm_user_is_valid(build_usr) and adaptavist.enabled:
        logging.warning("Local user '%s' is not known in Jira. Test cases will be reported without an executor!", build_usr)
        adaptavist.local_user = ""

    # Store metadata for later usage (e.g. adaptavist traceability).
    metadata: dict[str, str] = getattr(config, "_metadata", dict(os.environ))
    build_url = metadata.get("BUILD_URL", "")
    jenkins_url = metadata.get("JENKINS_URL", "")
    code_base = metadata.get("GIT_URL", get_code_base_url())
    branch = metadata.get("GIT_BRANCH", "")
    commit = metadata.get("GIT_COMMIT", "")
    adaptavist.build_url = "/".join(build_url.split("/")[:5]) if build_url and jenkins_url and build_url.startswith(jenkins_url) else build_url
    adaptavist.code_base = code_base.replace(":", "/").replace(".git", "").replace("git@", "https://") \
        if code_base and code_base.startswith("git@") \
        else code_base

    # Check, if correct branch is used
    if get_option_ini(config, "restrict_branch") and branch != get_option_ini(config, "restrict_branch_name"):
        raise ValueError(
            f'The branch "{branch}" cannot be used to report as reporting is restricted to "{get_option_ini(config, "restrict_branch_name")}" by configuration.'
        )

    # Print a header with useful information
    if adaptavist.reporter:
        adaptavist.reporter.section("ATM build meta data", bold=True)
        adaptavist.reporter.line(f"build_usr: {build_usr or 'unknown'}")
        adaptavist.reporter.line(f"build_url: {build_url or 'unknown'}")
        adaptavist.reporter.line(
            f"code_base: {code_base or 'unknown'} {(branch or 'unknown') if code_base else ''} {(commit or 'unknown') if code_base and branch else ''}")
        adaptavist.reporter.line(f"reporting: {'enabled' if adaptavist.enabled else 'disabled'}")


@pytest.hookimpl(tryfirst=True)
def pytest_report_teststatus(report: TestReport) -> tuple[str, str, tuple[str, dict[str, bool]]] | None:
    """Return result-category, shortletter and verbose word for status reporting."""
    if getattr(report, "blocked", False):
        return "blocked", "b", ("BLOCKED", {"blue": True})
    return None


class Blocked(Skipped):
    """Block exception used to abort test execution and set result status to 'Blocked'."""


@pytest.fixture
def meta_data(request: pytest.FixtureRequest) -> MetaDataFixture:
    """This can be used to store data inside of test methods."""
    adaptavist: PytestAdaptavist = request.config.pluginmanager.getplugin("_adaptavist")
    return adaptavist.test_result_data[request.node.nodeid.split("@")[0]]


@pytest.fixture
def meta_block(request: pytest.FixtureRequest) -> MetaBlockFixture:
    """
    This fixture can be used to create reports for test blocks/steps immediately during test method call.

    .. code-block:: python

       with meta_block(step):
           # do your thing here
           pytest.assume(...)

    """

    def get_meta_block(step: int | None = None,
                       timeout: int = META_BLOCK_TIMEOUT,
                       action_on_timeout: MetaBlock.Action = MetaBlock.Action.STOP_METHOD,
                       message_on_timeout: str = "The test step exceeded its timewindow and timed out.") -> MetaBlock:
        """Return a meta block context to process single test blocks/steps."""
        return MetaBlock(request, timeout=timeout, action_on_timeout=action_on_timeout, message_on_timeout=message_on_timeout, step=step)

    return get_meta_block
