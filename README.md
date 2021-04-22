# pytest-adaptavist

This [pytest](http://pytest.org) plugin generates test execution results within Jira Test Management ([tm4j](https://www.adaptavist.com/doco/display/KT/Managing+Tests+From+the+REST+API)).

# Table of Contents
- [Installation](#installation)
- [Getting Started](#getting-started)
- [Examples and Features](#examples-and-features)
    - [General Workflow](#general-workflow)
    - [Context Reporting](#context-reporting)
    - [Testcase Order](#testcase-order)
    - [Testcase Range](#testcase-range)
    - [Skipping vs. Blocking](#skipping-vs.-blocking)
    - [Callbacks](#callbacks)

## Installation

To install pytest-adaptavist, you can use (one of) the following command(s):
```
$ pip install pytest-adaptavist
```

To uninstall pytest-adaptavist, you can use the following command:
```
$ pip uninstall pytest-adaptavist
```

Test case selection and ordering (see below) are supported by default.

In order to access Adaptavist/Jira and create test runs and results in there, provide credentials `JIRA_SERVER, JIRA_USERNAME, JIRA_PASSWORD` as environment variables
and run your tests with
```
$ pytest --adaptavist
```

By default the terminal output is configured by the common pytest options.
To achieve a more readable format showing names and docstrings of test methods and even context blocks, run your tests with
```
$ pytest --pretty
```

## Getting Started

1. pytest-adaptavist searches for test methods named like ```test_<test_case_key>``` or ```test_<test_case_key>_<step>```
   where ```test_case_key``` is the key of the Jira test case excluding the project key (e.g. "T1") and ```step``` defines a single test script step (if existing). In order to build real test case key strings from test methods, the corresponding project key needs to be specified for each relevant class or single test methods by using markers (see examples below). Alternatively, ```test_case_key``` can be given as it appears in Adaptavist, but with hyphens replaced by underscores (e.g. "TEST_T1").
   Each of these kind of test methods is marked as Adaptavist test case for reporting appropriate results into Adaptavist test management. Any other test methods are processed as usual.

2. Finally, pytest-adaptavist needs either ```pytest.test_run_key``` to use an existing test run or ```pytest.project_key``` to create a new test run every time with collected test cases linked to it.
   In order to work properly, either of these parameters need to be specified at the very start of the test session.
   If both parameters are empty, neither test runs nor test results are created in Adaptavist test management.
   Please also note that any of these parameters mentioned here and in the following documentation can either be set programmatically or be provided as part of json config file (./config/global_config.json).

## Examples and Features

### General Workflow

pytest-adaptavist collects test cases (and single test steps) as mentioned above and prepares them for Adaptavist reporting.

```pytest.test_run_key``` is used to specify an existing test run. In this case, it is important to mention
that collected test cases must be linked to that test run.

Alternatively, if ```pytest.project_key``` is given and ```pytest.test_run_key``` is left empty, pytest-adaptavist creates a new test run every time with collected test cases linked to it. In this case, ```pytest.test_run_suffix``` can be used to create a meaningful test run name. In addition, ```pytest.test_plan_key``` is available to link the new created test run to an existing testplan.

New test plans can be created by specifying ```test_plan_suffix``` which is used as identifier to find existing test plans and must be unique. If there is a matching test plan, it will be used for creating new test runs. Else a new test plan is created within the given project and new test runs are linked to that. If both test plan key and suffix are missing, test runs are created just for the given project.

<em>Naming convention for new test plans and test runs within pytest_adaptavist:</em>
* <em>new test plans are named like ```<project key> <test plan suffix>```</em>
* <em>new test runs are named like ```<test plan name or project key> <test run suffix> <datetime now>```</em>

```pytest.test_case_keys``` can be used as an option to run only a subset of implemented test cases.
All others are skipped in this case. For new created test runs these test cases are excluded while for existing test runs the appropriate test case results stay as they are (if existing).

In addition, ```pytest.test_case_keys``` may contain test cases that are not implemented in the current python test script.
This can be useful in cases where the new test run also needs to include manual test cases (e.g. for later execution).
Furthermore, it is even possible to just create a new test run with only test cases that are not (yet) implemented.

If either of these parameters is missing, pytest-adaptavist tries to read appropriate values from config file (global_config.json).

Specifying a project key for relevant test classes or test methods can be done by using markers:
   ```python
   @pytest.mark.project(project_key="my project")
   ```
If project markers are not used, pytest-adaptavist is using ```pytest.project_key``` to build test case key strings.

To send additional data (comments, attachments) to Adaptavist, test methods can be extended by using plugin's meta data parameter.<br/>
(Note that for blocked or skipped methods, attachments will be ignored and only comments will be added to the test result).

#### Examples

This simple snippet shows some implementation of step 2 of test case ```myproject-T1``` using ```meta_data```:
   ```python
    @pytest.mark.project(project_key="myproject")
    class TestClass(object):

        def test_T1_2(self, meta_data):
            meta_data["comment"] = "unexpected result"
            attachment = io.StringIO()
            attachment.write("this is just a simple attachment")
            meta_data["attachment"] = attachment
            meta_data["filename"] = "content.txt"
            assert False
   ```

With each test step report the status of overall (or parent) test result is adjusted automatically, depending on the status of all other test step results.

If a step fails, the status of the overall test is set to ```Fail``` and stays at ```Fail``` no matter of upcoming results within that test run. Furthermore, an appropriate information about failure is appended to overall test result as additional comment. Given the example above, there would be a ```step 2 failed: unexpected result``` note added to the overall test result comment.

If there is a test method for the overall test, its (optional) comment is prepended to the existing comment. Given the following example, the final comment for test case ```myproject-T1``` would be ```all good<br />step 2 failed: unexpected result```:
   ```python
    @pytest.mark.project(project_key="myproject")
    class TestClass(object):

        def test_T1_2(self, meta_data):
            meta_data["comment"] = "unexpected result"
            attachment = io.StringIO()
            attachment.write("this is just a simple attachment")
            meta_data["attachment"] = attachment
            meta_data["filename"] = "content.txt"
            assert False

        def test_T1(self, meta_data):
            meta_data["comment"] = "all good"
            assert True
   ```
However, the final status would be ```Fail``` because not all test steps passed.

### Context reporting

In addition to implementing test methods for single test steps, it is possible to combine them within the appropriate test case method by using context blocks:
   ```python
    class TestClass(object):

        @pytest.mark.project(project_key="myproject")
        def test_T1(self, meta_block):
            # processing step 1
            with meta_block(1) as mb:
                mb.data["comment"] = "unexpected result"
                attachment = io.StringIO()
                attachment.write("this is just a simple attachment")
                mb.data["attachment"] = attachment
                mb.data["filename"] = "content.txt"
                pytest.assume(True)
            # processing step 2
            with meta_block(2) as mb:
                mb.data["comment"] = "unexpected result"
                attachment = io.StringIO()
                attachment.write("this is just a simple attachment")
                mb.data["attachment"] = attachment
                mb.data["filename"] = "content.txt"
                pytest.assume(False)

        @pytest.mark.project(project_key="myproject")
        def test_T2(self, meta_block):
            # processing test case only
            with meta_block() as mb:
                mb.data["comment"] = "all good"
                attachment = io.StringIO()
                attachment.write("this is just a simple attachment")
                mb.data["attachment"] = attachment
                mb.data["filename"] = "content.txt"
                pytest.assume(True)
   ```
It is highly recommended to use pytest.assume instead of assert in this case, as assert would immediately abort from current test method just skipping any other steps or context blocks. Alas, there might be cases, where it does make sense to abort though. In these cases, using assert is the better choice.

To simplify the overall handling, there's a helper method that combines meta data (e.g. comments, attachments) and assertion. Basically it checks given condition, aborts or continues appropriately and adds comments and attachments optionally:
   ```python
    class TestClass(object):

        @pytest.mark.project(project_key="myproject")
        def test_T2(self, meta_block):

            with meta_block() as mb:
                # if precondition is False, stop session (results in status "Blocked" for this and any following test cases)
                mb.check(precondition, message="precondition failed", action_on_fail=mb.Action.STOP_SESSION)
                # if precondition is False, stop further execution of this test (results in status "Blocked")
                mb.check(precondition, message="precondition failed", action_on_fail=mb.Action.STOP_METHOD)

                with meta_block(1) as mb1:
                    # if condition is False, just collect failed assumption and continue (just like 'assume', results in test step status "Fail")
                    mb1.check(condition, message="condition failed", action_on_fail=mb1.Action.FAIL_CONTEXT)
                    # if condition is False, stop further execution of this step (results in status "Blocked")
                    mb1.check(condition, message="condition failed", action_on_fail=mb1.Action.STOP_CONTEXT)
                    # if condition is False, stop further execution of this test (just like 'assert', results in status "Fail")
                    mb1.check(condition, message="condition failed", action_on_fail=mb1.Action.FAIL_METHOD)

                with meta_block(2) as mb2:
                    attachment = io.StringIO()
                    attachment.name = "context.txt"
                    attachment.write("this is just a simple attachment")
                    # default: if condition is False, just collect failed assumption and continue (just like 'assume', results in test step status "Fail")
                    mb2.check(condition, message="condition failed", attachment=attachment)  # attachment is added anyway
   ```
In addition, this method supports the following parameters:
* ```message_on_pass``` which can be used to report passed conditions as well
* ```message_on_fail``` which is the same as ```message``` (just for convenience)
* ```description``` as option to add details about test results (f.e. can be a html table or more)

### Testcase Order

By default the execution of test methods in pytest runs alphabetical over test class names and then from top to bottom.

With pytest-adaptavist this order can be changed by using ```pytest.test_case_order``` (or ```pytest.test_case_keys```, see also above).
In this case the corresponding test methods are executed according to the given order, followed by all remaining test methods.
Moreover, this can also be used when creating test runs automatically, as in this case the new test run is created with test cases linked in the given order.<br/>

Alternatively, if an existing test run is specified by ```pytest.test_run_key```, the corresponding test methods are executed according to the order of test cases in the given test run, followed by all other test methods.

Note that ```pytest.test_case_order``` overrules the test case order of the given test run as well as the order specified by ```pytest.test_case_keys```. This might be helpful in cases, where the default order should be changed temporarily. If ```pytest.test_case_order``` is not specified, the order will be as defined by ```pytest.test_run_key``` or - if a new test run should be created - ```pytest.test_case_keys```.

#### Examples:

Assume there is a project TEST with exactly two test cases TEST-T1 and TEST-T2 while a test implementation contains methods in the following order (top to bottom):<br/>
&nbsp;&nbsp;&nbsp;&nbsp;```test_T4```, ```test_T1```, ```test_T2```, ```test_T3```, ```test_myspecialtest```.

All these methods will be executed in the same order (from top to bottom). But a potentially new created test run will only contain TEST-T1 and TEST-T2 (in this order). And only the results of TEST-T1 and TEST-T2 will be send to Adaptavist.

For the next run a test case order is specified like TEST-T2, TEST-T3, TEST-T18.
Now the methods are executed in this order:<br/>
&nbsp;&nbsp;&nbsp;&nbsp;```test_T2```, ```test_T3```, ```test_T4```, ```test_T1```, ```test_myspecialtest```.

As we can see, all the test cases specified in the test case order are executed first followed by all the others.
Of course, TEST-T18 is ignored as there is no implementation found.<br/>
Again, a potentially new created test run will only contain TEST-T2 and TEST-T1 (in this order).

For cases where a new test run should be created including only a subset of testcases, it is enough to specify ```pytest.test_case_keys``` only by using the required order. All listed test cases are linked (and executed, if implemented) in exactly this order.

### Testcase Range

In addition to specify a list of test cases to be executed it is possible to define ranges of test cases by using ```pytest.test_case_range```.

#### Examples:

Defining ```["TEST-T2", "TEST-T5", "TEST-200", "TEST-299"]``` as a range will include any test cases from TEST-T2 to TEST-5 and from TEST-200 to TEST-299.

Similar to the use of ```pytest.test_case_keys``` all others are skipped in this case. For new created test runs these test cases are excluded while for existing test runs the appropriate test case results stay as they are (if existing).

### Skipping vs. Blocking

The execution of test cases (methods) or even single steps can be skipped, either **statically** or **dynamically**.

While **static skipping** is done f.e. by specifiying ```pytest.test_case_keys``` (only the listed test cases will be executed) or by applying appropriate markers as described below, **dynamic skipping** is happening based on some condition.

Basically, when a test case or step is skipped the status stays untouched (typically it will be "Not Executed").

According to Adaptavist test management, test cases with containing at least one step passed and all others not executed (yet) will have the status "In Progress" while test runs/cycles containing at least one test case being "Not Executed" or "In Progress" will have the status "In Progress".
This can be challenging when checking if a test runs/cycles is still running or is finished with some test cases skipped.
To solve this there is the option of blocking which is actually the same as skipping but with marking the test case (or step) as "Blocked".
Having any test cases or steps that have been aborted or not executed marked as "Blocked" will lead to a test run/cycle status "Done" once it is finished.

#### Using markers

Methods to skip or block test cases (methods) statically are provided by the markers ```pytest.mark.skip``` (part of pytest module) and 
```pytest.mark.block``` (defined in pytest-adaptavist):
   ```python
    class TestClass(object):

        @pytest.mark.skip(reason="not implemented yet")
        @pytest.mark.project(project_key="myproject")
        def test_T1(self, meta_block):
            ...

        @pytest.mark.block(reason="not implemented yet")
        @pytest.mark.project(project_key="myproject")
        def test_T2(self, meta_block):
            ...
   ```
Note that these markers work for classes as well.

#### Using metablock action modes

Methods to skip or block test cases (or steps) dynamically, e.g. depending on some condition, are provided by the meta block's helper method:
   ```python
    class TestClass(object):

        @pytest.mark.project(project_key="myproject")
        def test_T2(self, meta_block):

            with meta_block() as mb:
                # if precondition is False, stop session (results in status "Blocked" for this and any following test cases)
                mb.check(precondition, message="precondition failed", action_on_fail=mb.Action.STOP_SESSION)
                # if precondition is False, stop further execution of this test (results in status "Blocked")
                mb.check(precondition, message="precondition failed", action_on_fail=mb.Action.STOP_METHOD)

                with meta_block(1) as mb1:
                    # if condition is False, stop further execution of this step (results in status "Blocked")
                    mb1.check(condition, message="condition failed", action_on_fail=mb1.Action.STOP_CONTEXT)
            ...
   ```

#### Using pytest methods

Another methods to skip or block test cases (or steps) dynamically, e.g. depending on some condition, are ```pytest.skip``` (part of pytest module) and 
```pytest.block``` (defined in pytest-adaptavist):
   ```python
    def my_internal_function_1(...):
        ...
        if not precondition:
            pytest.skip(msg="precondition failed")
        ...

    def my_internal_function_2(...):
        ...
        if not precondition:
            pytest.block(msg="precondition failed")
        ...
   ```
Note that these methods are not needed usually, alas sometimes they can be useful inside of helper functions where test case context or information is missing.

### Callbacks

For additional custom functionality pytest-adaptavist provides a small set of callbacks:
```python

    def meta_block_condition_cb(signature, condition, reference):
        """
        Called with each call of mb.check
        providing a signature like <item name>_<step index>_<#calls>, the condition (True|False) and a reference message (message_on_pass|message_on_fail).
        """
        pass

    def meta_block_cb(signature, status):
        """
        Called when exiting a meta block (resp. context block)
        providing a signature like <item name>_<step index> and the final status ("passed", "failed", etc.).
        """
        pass
   ```

Examples below show how to work with them:
```python

    def my_func(a, b, c, d, **kwargs):
        """The actual function to be called."""
        print("my_func", a, b, c, d, kwargs)


    def my_callback_example_1(func, *args):
        """Wrapper for the condition callback."""
        def _cb(**kwargs):
            condition = kwargs.pop("condition", None)
            if not condition:
                return func(*args, **kwargs)
            return None
        return _cb


    def my_callback_example_2(func, *args):
        """Another example of a callback wrapper using lambda expression."""
        return lambda **kwargs : func(*args, **kwargs) if not kwargs.pop("condition", False) else None


    def my_callback_example_3(func, *args):
        """Wrapper for meta block callback."""
        def _cb(**kwargs):
            status = kwargs.pop("status", None)
            if status != "passed":
                return func(*args, **kwargs)
            return None
        return _cb


    def my_callback_example_4(func, *args):
        """Another example of a callback wrapper using lambda expression."""
        return lambda **kwargs : func(*args, **kwargs) if kwargs.pop("status", None) != "passed" else None


    @pytest.fixture(scope="function", autouse=True)
    def my_fixture_example(request):
        """Function-scoped fixture to set the callbacks."""
        request.node.meta_block_condition_cb = my_callback_example_1(my_func, 17, 18, 19)
        request.node.meta_block_cb = my_callback_example_3(my_func, 17, 18, 19)
   ```
