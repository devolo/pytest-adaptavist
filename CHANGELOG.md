# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.0] - 2021/11/17

## Added

* New options restrict_user and restrict_branch to control reporting to tm4j
* Exit the complete session on failure by using actions FAIL_EXIT_SESSION or STOP_EXIT_SESSION

## Changed

* At least Python 3.8 is required
* *BREAKING*: Pretty option was removed. If you use it, please switch to [pytest-pretty-terminal](https://github.com/devolo/pytest-pretty-terminal)
* *BREAKING*: Unless you use the new options, reporting is no longer restricted

## Fixed

* Attaching multiple files at a time now works as expected
* Configuration values evaluated to False now work as expected
* Integer configuration values now work as expected

## [4.0.6] - 2021/04/22

## Added

* Duration of a test step can now be limited with a timeout, defaults to 10 minutes.

## [4.0.5] - 2020/02/06

## Changed

* Reversed application of test case order and range to be more intuitive
* Changed plugin to work even without jstyleson and pytest-xdist being installed

### Fixed

* Fixed final status line in case of NOT_BUILT status
* Fixed identification of test case siblings in case of parametrized or repeated methods
* Resolved issues at different variations of test methods and results

## [4.0.0] - 2020/02/06

First publicly available version.
