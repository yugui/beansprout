# Beansprout

This project provides a custom command `bean-sprout` on top of the Beancount
doube-entry bookkeeping system. The command provides more convenient features
than the ones in the plain beancount, assuming certain conventions of ledger
directory structure as we discuss later.

## Beancount
Beancount is a text-based double-entry bookkeeping system.
Ledger files have an extension `.beancount` by convention, and they can be
split into multiple files and include other files.

You can refer the following docs for the basic idea of Beancount:
* [Beancount User's Manual](https://beancount.github.io/docs/index.html)
  * [Getting Started with Beancount](https://beancount.github.io/docs/getting_started_with_beancount.html)
  * [Beancount Language Syntax](https://beancount.github.io/docs/beancount_language_syntax.html)
* [Fava](https://beancount.github.io/fava/index.html) gives web UI for leadgers
  in the beancount format.

# Ledger Directory Structure
While Beancount itself does not assume any specific structure to organize ledger
files with, Beansprout assumes the following one for convenience:

* foo.beancount -- the primary .beancount file at the root directory. It directly
  or indirectly include other .beancount files in the structure. Usually it is
  named after the root directory name, but you can be named differently. Users need
  to pass the filename to `bean-sprout` command.
* config/ -- relatively-static "configurations" for the ledger reside in the
  .beancount files under this directory. For example, option directives or commodity
  directives can belong to them.
* quotes/ -- prices of commodities are organized here
  * FOO/ -- each commodity has its own subdirectory, named after their symbol
    * main.beancount -- Each comodity subdirectory has `main.beancount`, which include
      all other .beancount files in the directory.
    * ${YYYYmm}.beancount -- prices of the commodity are grouped by their calendar
      year and month, and belong to files that are named after the year and the month.
* transactions/ -- individual transactions are recorded under this directory
  * Assets/
    * Foo/Bar/Baz/ -- each account in the ledger can have its corresponding
      subdirectory, named after the acount name. For example, the account
      Assets:Foo:Bar:Baz would have this subdirectory path.
      Not all accounts necessarily have its subdirectory. It has the one only if
      Beansprout (or the user) wants to record transactions on the account.
      * main.beancount -- Each subdirectory of account has `main.beancount`, which
        include all other .beancount files in the directory.
      * ${YYYYmm}.beancount -- transactions are grouped by their calendar year and
        month.
  * Liabilities/
  * Equity/
  * Expenses/
  * Income/ -- Similary, other kinds of accounts have similar structure.
