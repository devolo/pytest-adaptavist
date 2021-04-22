from setuptools import setup

setup(
    name="pytest-adaptavist",
    description="pytest plugin for generating test execution results within Jira Test Management (tm4j)",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    version="v4.0.6",
    url="https://github.com/devolo/pytest-adaptavist",
    author="Stephan Steinberg",
    author_email="stephan.steinberg@devolo.de",
    license="MIT",
    py_modules=["pytest_adaptavist"],
    entry_points={"pytest11": ["adaptavist = pytest_adaptavist"]},
    platforms="any",
    python_requires=">=3.6",
    install_requires=["adaptavist>=1.0.0", "pytest>=3.4.1"],
    keywords="python pytest adaptavist kanoah tm4j jira test testmanagement report",
    classifiers=[
        "Framework :: Pytest",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Topic :: Utilities",
        "Topic :: Software Development :: Libraries :: Python Modules"
    ]
)

