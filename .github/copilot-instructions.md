# BeanCount

This project provides a set of custom commands and their underlying python
packages on top of the Beancount doube-entry bookkeeping system.

You can refer the following docs for the basic idea of Beancount:
* [Beancount User's Manual](https://beancount.github.io/docs/index.html)
  * [Getting Started with Beancount](https://beancount.github.io/docs/getting_started_with_beancount.html)
  * [Beancount Language Syntax](https://beancount.github.io/docs/beancount_language_syntax.html)
  * [Beancount v3 Design Doc](https://docs.google.com/document/d/1qPdNXaz5zuDQ8M9uoZFyyFis7hA0G55BEfhWhrVBsfc/edit?tab=t.0)
* [Fava](https://beancount.github.io/fava/index.html) gives web UI for leadgers
  in the beancount format.

Beancount supports custom extensions of price quotes of commodities, importing
transactions from other formats, and more pages in the Fava UI.
You can write python libraries on top of the APIs in the following pypi packages
when you want to give such customizations:
* `beancount` -- The basic package
* `beangulp` -- The framework for custom transaction importers
* `beanprice` -- The price quotes fetcher
* `fava` -- The web UI

# Toolchains
* This project uses Bazel as the build system. You must maintain the Bazel build
  configurations consistently with the source code. You must use Bazel for
  running and testing the code.
  * The version of Bazel is recorded in the `.bazeliskrc` file.
* The commands and their underlying packages are written in Python. You must
  use Python 3.13 or later for the code.
  * The version of Python is managed by the `rules_python` Bazel
    dependency.

# Development Cycle
The development cycle is as follows:
1. A new feature, a bug fix, refactors, or a new command is proposed
2. Discuss the overall design and the intermediate goals
   * Get the design reviewed and approved by me
3. Repeat the following steps for each intermediate goal
   1. Clarify the class-level or function-level design
   2. Get the design reviewed and approved by me
   3. Implement the design with TDD
   4. Make sure that all tests are passed and all files are well-formatted
   5. Make a git commit with a description that explains the design overview.
      The description should not repeat the code-level changes.
4. Explain the example usage for the new feature or a new command
5. Back to the step 2 if necessary

You can simply use the main branch for development. You do not need to create a
new branch for each.

# Source Structure
* `third_party/` -- any third-party library dependencies
* `beansprout/` -- our custom implementation of Beancount extensions
  * `importer/` -- custom importer libraries for transaction importing
    * `importers/` -- specific importer implementations for various financial institutions
      * `moneyforward.py` -- importer for MoneyForward ME CSV files
  * `quoter/` -- custom price quoters for fetching commodity prices
    * `sources/` -- specific price source implementations
* `data/` -- data files for the project

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

## Formatting
The code should be formatted with the following formatters before you make git
commits.

* `buildifier` -- for Bazel files
* `yapf` -- for python files. You need to pass `-i` option to in-place edit.

# Third-party dependencies
You need to maintain the third-party dependencies in the `third_party/`
directory.

`reqruirements.in` in the directory defines the direct dependencies on PyPI
packages. You need to run `bazel run //third_party:requirements.update` to
consistently update `requirements_lock.txt`.

You can make sure that the dependencies are locally available by running
`bazel build @beancount_deps//...`. Then, you will have the dependency
packages resolved and downloaded in the `bazel-beancount/external/` directory.
The directory contains symlinks to the actual resolved package directories.
Such symlinks are suffixed with `rules_python++` and contains the package
name in the file names.

You can refer the files under the individual linked directories to see the
source of the packages like `beancount`, `beangulp`.

# API References
You can refer the following reference implementations and API references for
the custom packages:

* https://beancount.github.io/docs/api_reference/index.html for the Beancount
  package
* `examples/` directory in the `beangulp` package for custom importers
* `beanprice/sources` directory in the `beanprice` package for custom price
  quoters.
* [Fava API Reference](https://beancount.github.io/fava/api.html) for Fava UI
  extensions
