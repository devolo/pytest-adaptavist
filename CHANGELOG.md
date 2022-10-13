# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.8.0] - 2022/10/13

### Added

* Allow attaching StringIO objects

### Fixed

* Tests are skipped, if an invalid test cycle is configured
* Tests are skipped, if the Jira credentials are wrong

## [5.7.3] - 2022/06/07

### Fixed

* Jira cycle information are build correctly again

## [5.7.2] - 2022/06/07

### Fixed

* Jira settings are also properly defined to avoid warnings

## [5.7.1] - 2022/06/07

### Fixed

* Settings are properly defined to avoid warnings

## [5.7.0] - 2022/05/31

### Added

* Define settings in pytest.ini as alternative to global_config.json

## [5.6.2] - 2022/05/30

### Fixed

* Fix item collection in case no test cases are selected

## [5.6.1] - 2022/05/24

### Fixed

* Fixed simultaneously use of test_case_keys in config and --append-to-cycle

## [5.6.0] - 2022/05/17

### Added

* Add support for appending not attached testcases to a test run if the test cycle key is given. Use it with the option '--append-to-cycle'

### Deprecated

* --test_run_name is deprecated now and will be removed in pytest-adaptavist 6. Use --test-cycle-name instead
* --test_plan_name is deprecated now and will be removed in pytest-adaptavist 6. Use --test-plan-name instead

## [5.5.0] - 2022/04/26

### Added

* Add support for test case decorator

## [5.4.0] - 2022/04/04

### Added

* Define test run and test plan names in pytest.ini

## [5.3.0] - 2022/03/25

### Added

* blockif decorator

### Fixed

* The parameter for timeouts had a nasty typo

## [5.2.0] - 2022/03/22

### Added

* Choose an action and a message on timeout

### Fixed

* Docstrings of actions

## [5.1.4] - 2022/02/22

### Fixed

* Testcases which are skipped due to test_case_keys are no longer reported to adaptavist

## [5.1.3] - 2022/02/14

### Fixed

* Fixed project key handling if set in global config and using the project marker

## [5.1.2] - 2022/02/01

### Fixed

* Handle xdist groups correctly
* Handle project marker correctly

## [5.1.1] - 2022/01/27

### Fixed

* Stack trace on failed assumptions is correct again.

## [5.1.0] - 2022/01/21

### Added

* Blocked test cases comments now also get a badge

### Changed

* The date format in comments is formatted now as %Y-%m-%d %H:%M

### Fixed

* Summary urls are build up correctly
* Prevent the same comment in testcases

## [5.0.1] - 2021/11/30

### Fixed

* We need a higher version of pytest-assume to use the hook pytest_assume_summary_report

## [5.0.0] - 2021/11/24

### Added

* New options restrict_user and restrict_branch to control reporting to tm4j
* Exit the complete session on failure by using actions FAIL_EXIT_SESSION or STOP_EXIT_SESSION

### Changed

* At least Python 3.8 is required
* *BREAKING*: Pretty option was removed. If you use it, please switch to [pytest-pretty-terminal](https://github.com/devolo/pytest-pretty-terminal)
* *BREAKING*: Unless you use the new options, reporting is no longer restricted

### Fixed

* Attaching multiple files at a time now works as expected
* Configuration values evaluated to False now work as expected
* Integer configuration values now work as expected

## [4.0.6] - 2021/04/22

### Added

* Duration of a test step can now be limited with a timeout, defaults to 10 minutes.

## [4.0.5] - 2020/02/06

### Changed

* Reversed application of test case order and range to be more intuitive
* Changed plugin to work even without jstyleson and pytest-xdist being installed

### Fixed

* Fixed final status line in case of NOT_BUILT status
* Fixed identification of test case siblings in case of parametrized or repeated methods
* Resolved issues at different variations of test methods and results

## [4.0.0] - 2020/02/06

First publicly available version.
