# Instructions for AI Agents

This file is an instruction for the AI agents. You (the AI agents) should
follow the instructions in this file when you are asked to do something
related to the project. You should not modify this file or involve it into
git commits unless I (the human) ask you to do so.

# Development Cycle
The development cycle is as follows:
1. A new feature, a bug fix, refactors, or a new command is proposed
2. Discuss the overall design and the intermediate goals
   * Get the design reviewed and approved by me
3. Repeat the following steps for each intermediate goal
   1. Clarify the class-level or function-level design
   2. Get the design reviewed and approved by me
   3. Implement the design in Test-Driven Development
      * Therefore, you must write unit tests before you implement the code
   4. Make sure that all tests are passed and all files are well-formatted
      * All Bazel tests are passing (`bazel test //...`)
      * All `py_binary` targets successfully exit when passed the `--help` option
      * All files are properly formatted using the required formatters:
        * `buildifier` for Bazel files
        * `yapf -i` for Python files
   5. Make a git commit with a description that explains the design overview.
      The description should not repeat the code-level changes.
4. Explain the example usage for the new feature or a new command
5. Back to the step 2 if necessary

You can simply use the main branch for development. You do not need to create a
new branch for each.

## Larger Changes
You must propose a high-level design at first, and break down the design goals
into smaller intermediate goals when you work on larger changes.
Then, you must get the plan reviewed and approved by me before you start
working on the individual steps. Individual steps should stay small and
self-contained, and they should independently follow the development cycle.

You should ask me questions when the requirements are not clear, or when you
need to clarify the design. Although It is encouraged to make reasonable
assumptions, you should explain the assumptions in the design proposal.

# Toolchains
* This project uses Bazel as the build system. You must maintain the Bazel build
  configurations consistently with the source code. You must use Bazel for
  running and testing the code.
  * The version of Bazel is recorded in the `.bazeliskrc` file.
* The commands and their underlying packages are written in Python. You must
  use Python 3.13 or later for the code.
  * The version of Python is managed by the `rules_python` Bazel
    dependency.

## Coding Principles

### Python
* Python files have docstrings at the top of the file, and all functions and
  classes. The docstrings should be maintained consistently with the code.
* All functions have type hints.
* Prefer named parameters over positional parameters when you call a function
  with more than 3 parameters or when the parameters are not self-explanatory.
* Prefer namedtuple over tuple when you need to have more than three elements
  in a tuple or the arguments are not self-explanatory.

### Bazel
* We use `rules_python` for managing the python dependencies.
* We use bzlmod for managing the Bazel dependencies.
* The Bazel build files are named `BUILD.bazel` and `MODULE.bazel` files.
* `glob` function in the build configurations are discouraged. You should
  explicitly list the filename attributes.

# About the Project

This project provides a custom command `bean-sprout` on top of the Beancount
double-entry bookkeeping system. The command provides more convenient features
than those in plain Beancount, such as:

- Automatic merging of new transactions into existing files by assuming the file path
  where the new transactions are recorded
- Simplified workflow for managing Beancount ledgers through a consistent directory
  structure

You should take a look at `README.md` for the high-level product definition
of this repository, and about the overall idea of Beancount itself.

## Ledger Directory Structure
Beansprout assumes a specific directory structure for organizing ledger files, which
is described in detail in `README.md`. This structure enables many of the automated
features that make Beansprout more convenient than plain Beancount.

# Source Structure
* `third_party/` -- any third-party library dependencies
* `beansprout/` -- our custom implementation of Beancount extensions
  * `importer/` -- custom importer libraries for transaction importing
    * `importers/` -- specific importer implementations for various financial institutions
      * `moneyforward.py` -- importer for MoneyForward ME CSV files
  * `quoter/` -- custom price quoters for fetching commodity prices
    * `sources/` -- specific price source implementations
* `data/` -- data files for the project

# Third-party dependencies
You need to maintain the third-party dependencies in the `third_party/`
directory.

`reqruirements.in` in the directory defines the direct dependencies on PyPI
packages. You need to run `bazel run //third_party:requirements.update` to
consistently update `requirements_lock.txt`.

You can make sure that the dependencies are locally available by running
`bazel build @beansprout_deps//...`. Then, you will have the dependency
packages resolved and downloaded in the `bazel-beansprout/external/` directory.
The directory contains symlinks to the actual resolved package directories.
Such symlinks are suffixed with `rules_python++` and contains the package
name in the file names.

You can refer the files under the individual linked directories to see the
source of the packages like `beancount`, `beangulp`.

## Base Libraries
Beancount supports custom extensions of price quotes of commodities, importing
transactions from other formats, and more pages in the Fava UI.
You can write python libraries on top of the APIs in the following pypi packages
when you want to give such customizations:
* `beancount` -- The basic package
* `beangulp` -- The framework for custom transaction importers
* `beanprice` -- The price quotes fetcher
* `fava` -- The web UI

## API References
You can refer the following reference implementations and API references for
the custom packages:

* https://beancount.github.io/docs/api_reference/index.html for the Beancount
  package
* `examples/` directory in the `beangulp` package for custom importers
* `beanprice/sources` directory in the `beanprice` package for custom price
  quoters.
* [Fava API Reference](https://beancount.github.io/fava/api.html) for Fava UI
  extensions

