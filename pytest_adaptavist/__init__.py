"""This module provides a set of pytest hooks for generating Adaptavist test run results from test reports."""

import logging
import os
from importlib.metadata import PackageNotFoundError, version
from typing import Callable, Dict, Optional, Tuple

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.fixtures import FixtureRequest
from _pytest.nodes import Node
from _pytest.outcomes import Skipped, _with_exception
from _pytest.reports import TestReport

from ._atm_configuration import atm_user_is_valid
from ._helpers import get_code_base_url
from ._pytest_adaptavist import PytestAdaptavist
from .metablock import MetaBlock

try:
    __version__ = version("adaptavist")
except PackageNotFoundError:
    # package is not installed - e.g. pulled and run locally
    __version__ = "0.0.0"

META_BLOCK_TIMEOUT = 600


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config):
    """Prepare and start logging/reporting (called at the beginning of the test process)."""

    # register custom markers
    config.addinivalue_line("markers", "testcase: mark test method as test case implementation (for internal use only)")
    config.addinivalue_line("markers", "project(project_key): mark test method to be related to given project (used to create appropriate test case key")
    config.addinivalue_line("markers", "block(reason): mark test method to be blocked")

    if config.getoption("-h") or config.getoption("--help"):
        return

    adaptavist = PytestAdaptavist(config)
    config.pluginmanager.register(adaptavist, "_adaptavist")

    # support for pytest.block
    @_with_exception(Blocked)
    def block(msg=""):
        __tracebackhide__ = True  # pylint: disable=unused-variable
        raise Blocked(msg=msg)

    pytest.block = block

    # Store metadata for later usage (e.g. adaptavist traceability).
    metadata = getattr(config, "_metadata", os.environ)

    build_usr = "jenkins"  # TODO: REVERT THIS!!!!
    build_url = metadata.get("BUILD_URL")
    jenkins_url = metadata.get("JENKINS_URL")
    code_base = metadata.get("GIT_URL", get_code_base_url())
    branch = metadata.get("GIT_BRANCH")
    commit = metadata.get("GIT_COMMIT")

    adaptavist.build_url = "/".join(build_url.split("/")[:5]) if build_url and jenkins_url and build_url.startswith(jenkins_url) else build_url
    adaptavist.code_base = code_base.replace(":", "/").replace(".git", "").replace("git@", "https://") \
        if code_base and code_base.startswith("git@") \
        else code_base

    # only report results to adaptavist if:
    #     - branch is master
    #     - user is jenkins
    #     - env is jenkins
    # note: we might need the possibility to create adaptavist results from a local test run (beit for testing purpose or whatever)

    # if user is jenkins
    #   if branch is master then report using getpass.getuser()
    #   else disable report
    # else
    #   report using getpass.getuser()

    # => automated flag set and executedby = "jenkins" means official test run
    # => automated flag set and executedby != "jenkins" means inofficial test run (not valid with respect to DoD)
    if build_usr == "jenkins" and build_url and jenkins_url and build_url.startswith(jenkins_url) and branch != "origin/master":
        # disable reporting
        setattr(config.option, "adaptavist", False)

    if build_usr != "jenkins" and not atm_user_is_valid(build_usr):
        # disable reporting
        setattr(config.option, "adaptavist", False)

    # TODO: REMOVE BEFORE RELEASE!!!!!!!
    setattr(config.option, "adaptavist", True)

    if adaptavist.reporter:
        adaptavist.reporter.section("ATM build meta data", bold=True)

        adaptavist.reporter.line(f"build_usr: {build_usr or 'unknown'}")
        adaptavist.reporter.line(f"build_url: {build_usr or 'unknown'}")
        adaptavist.reporter.line(
            f"code_base: {code_base or 'unknown'} {(branch or 'unknown') if code_base else ''} {(commit or 'unknown') if code_base and branch else ''}")
        adaptavist.reporter.line(f"reporting: {'enabled' if getattr(config.option, 'adaptavist', False) else 'disabled'}")

    logger = logging.getLogger("pytest-adaptavist")
    logger_handler = logging.StreamHandler()
    logger_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(logger_handler)
    logger.propagate = False


class Blocked(Skipped):
    """Block exception used to abort test execution and set result status to 'Blocked'."""


def pytest_addoption(parser: Parser):
    """Add options to control plugin."""
    group = parser.getgroup("adaptavist", "adaptavist test reporting")
    group.addoption("--adaptavist", action="store_true", default=False, help="Enable adaptavist reporting (default: False)")


@pytest.hookimpl(trylast=True)
def pytest_configure_node(node: Node):
    """This is called in case of using xdist to pass data to worker nodes."""
    if node.config.pluginmanager.hasplugin("xdist"):
        node.workerinput["options"] = {"dist": node.config.option.dist, "numprocesses": node.config.option.numprocesses}


@pytest.hookimpl()
def pytest_report_teststatus(report: TestReport) -> Optional[Tuple[str, str, Tuple[str, Dict[str, bool]]]]:
    """Return result-category, shortletter and verbose word for status reporting."""
    if getattr(report, "block", False):
        return "blocked", "b", ("BLOCKED", {"blue": True})
    return None


@pytest.fixture(scope="function")
def meta_data(request: FixtureRequest):
    """This can be used to store data inside of test methods."""
    adaptavist: PytestAdaptavist = request.config.pluginmanager.getplugin("_adaptavist")
    return adaptavist.test_result_data[request.node.fullname]


@pytest.fixture(scope="function")
def meta_block(request: FixtureRequest) -> Callable[[Optional[int], int], MetaBlock]:
    """This can be used to create reports for test blocks/steps immediately during test method call.
        ```
        with meta_block(step):
            # do your thing here
            pytest.assume(...)
        ```
    """

    def get_meta_block(step: Optional[int] = None, timeout: int = META_BLOCK_TIMEOUT) -> MetaBlock:
        """Return a meta block context to process single test blocks/steps."""
        return MetaBlock(request, timeout=timeout, step=step)

    return get_meta_block
