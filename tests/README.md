# pytest-adaptavist Tests

This test suite contains unit tests and system tests. In order to make the system tests work in your enviroment, certain preconditions have to be met. Otherwise, they will be skipped.

# Preconditions

First, create a file config/global_config.json at the root of this project (not the root of the tests). This file should contain the following content:
```
{
    "project_key": <Project key to report to>,
    "jira_server": <URL of your Jira instance>,
    "jira_username": <Username to login with>,
    "jira_password": <Password to login with>,
}

Second, import test_case_template.csv to your Jira instance to have a test cases in place.

# Run the tests

To only run unit tests, run
```
$ pytest -m "not system"
```

To only run system tests, run
```
$ pytest -m "system"
```

To run both, run
```
$ pytest
```
