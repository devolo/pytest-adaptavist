"""Make plugin compatible with pytest-xdist."""

import pytest
from _pytest.nodes import Node


class XdistHooks:
    """Hooks for xdist"""

    @staticmethod
    @pytest.hookimpl(trylast=True)
    def pytest_configure_node(node: Node):
        """This is called in case of using xdist to pass data to worker nodes."""
        node.workerinput["options"] = {"dist": node.config.option.dist, "numprocesses": node.config.option.numprocesses}  # type: ignore
