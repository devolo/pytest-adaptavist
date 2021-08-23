"""Read config parameters."""
import json
import os
from datetime import datetime
from typing import Any, Optional

import pytest
from adaptavist import Adaptavist


class ATMConfiguration:
    """Configuration class to read config parameters (either from env or from "global_config.json")."""

    def __init__(self):
        """Constructor."""
        self.config = {}
        config_file_name = os.path.join("config", "global_config.json")
        if os.path.exists(os.path.abspath(config_file_name)):
            with open(config_file_name, "r") as config_file:
                try:
                    self.config.update(json.load(config_file))
                except Exception as ex:
                    raise ValueError("Failed to load config from file \"{0}\"!".format(config_file), ex) from ex

    def get(self, key: str, default: Any = None) -> Any:
        """Get value either from environment or from config file."""

        if key.lower().startswith("cfg_"):
            return self.config.get(key) or default
        return os.environ.get(key) or os.environ.get(key.upper()) or self.config.get("cfg_" + key) or self.config.get(key) or default

    def get_bool(self, key: str, default: Any = None) -> Optional[bool]:
        """Get boolean value either from environment or from config file."""

        result = self.get(key=key, default=default)

        if isinstance(result, bool) or result is None:
            return result

        if result.lower() in ["true", "1", "yes"]:
            return True

        if result.lower() in ["false", "0", "no"]:
            return False

        raise ValueError(f"Invalid bool result: {result}")


def atm_user_is_valid(user: str) -> bool:
    """Check if user is known to Adaptavist/Jira."""
    cfg = ATMConfiguration()
    return user in Adaptavist(cfg.get("jira_server", ""), cfg.get("jira_username", ""), cfg.get("jira_password", "")).get_users()


def atm_configure(config) -> bool:
    """Setup adaptavist reporting based on given requirements (config)."""
    cfg = ATMConfiguration()

    if not getattr(pytest, "adaptavist", None):
        pytest.adaptavist = Adaptavist(cfg.get("jira_server", ""), cfg.get("jira_username", ""), cfg.get("jira_password", ""))
    if not getattr(pytest, "project_key", None):
        pytest.project_key = cfg.get("project_key", None)

    # support of multiple environments
    # in case of using xdist's "each" mode, a test run for each specified environment is created
    # and test_environment can be used (when given as a list or comma-separated string) to specify keys for each test run resp. worker node
    worker_input = getattr(config, "workerinput", {})
    distribution = worker_input.get("options", {}).get("dist", None)
    index = int(worker_input.get("workerid", "gw0").split("gw")[1]) if (distribution == "each") else 0

    entry = getattr(pytest, "test_environment", []) or cfg.get("test_environment", []) or []
    test_environments = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry
    pytest.test_environment = test_environments[index if index < len(test_environments) else -1] if test_environments else None

    entry = getattr(pytest, "test_case_keys", []) or cfg.get("test_case_keys", []) or []
    pytest.test_case_keys = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    entry = getattr(pytest, "test_case_order", []) or cfg.get("test_case_order", []) or []
    pytest.test_case_order = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    entry = getattr(pytest, "test_case_range", []) or cfg.get("test_case_range", []) or []
    pytest.test_case_range = [x.strip() for x in entry.split(",")] if isinstance(entry, str) else entry

    if not getattr(pytest, "test_plan_key", None):
        pytest.test_plan_key = cfg.get("test_plan_key", None)
    if not getattr(pytest, "test_plan_folder", None):
        pytest.test_plan_folder = cfg.get("test_plan_folder", None)
    if not getattr(pytest, "test_plan_suffix", None):
        pytest.test_plan_suffix = cfg.get("test_plan_suffix", None)
    if not getattr(pytest, "test_run_key", None):
        pytest.test_run_key = cfg.get("test_run_key", None)
    if not getattr(pytest, "test_run_folder", None):
        pytest.test_run_folder = cfg.get("test_run_folder", None)
    if not getattr(pytest, "test_run_suffix", None):
        pytest.test_run_suffix = cfg.get("test_run_suffix", "test run " + datetime.now().strftime("%Y%m%d%H%M"))
    if getattr(pytest, "skip_ntc_methods", None) is None:
        pytest.skip_ntc_methods = cfg.get_bool("skip_ntc_methods", False)

    return True
