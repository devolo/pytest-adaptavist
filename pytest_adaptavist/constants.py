"""Constants used by the module."""

COLORMAP = {
    "passed": {
        "green": True, "bold": True
    },
    "failed": {
        "red": True, "bold": True
    },
    "blocked": {
        "blue": True, "bold": True
    },
    "skipped": {
        "yellow": True, "bold": True
    }
}

META_BLOCK_TIMEOUT = 600

TEST_RUN_NAME_DEFAULT = "%(project_key) %(test_run_suffix)"
TEST_PLAN_NAME_DEFAULT = "%(project_key) %(test_plan_suffix)"
