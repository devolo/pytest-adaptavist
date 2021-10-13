"""Test compatibility with pytest-xdist."""

from unittest.mock import patch

import pytest


class TestXdistUnit:
    """Test compatibility with pytest-xdist on unit test level."""

    @pytest.mark.usefixtures("adaptavist")
    def test_xdist_handling(self, pytester: pytest.Pytester):
        """Test coexistence with xdist."""
        pytester.makepyfile("""
            import pytest

            def test_dummy():
                assert True
        """)
        with patch("_pytest.config.PytestPluginManager.hasplugin", return_value=True):
            config = pytester.parseconfigure("--adaptavist")
            assert config.pluginmanager.getplugin("_xdist_adaptavist")
        with patch("_pytest.config.PytestPluginManager.hasplugin", return_value=False):
            config = pytester.parseconfigure("--adaptavist")
            assert not config.pluginmanager.getplugin("_xdist_adaptavist")
