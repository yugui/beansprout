# Beansprout

This project provides a custom command `bean-sprout` on top of the Beancount
doube-entry bookkeeping system. The command provides some convenience features,
assuming a certain directory structure of ledger files.

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

* `ledger.beancount` -- the primary `.beancount` file at the root directory. It
  directly or indirectly include other .beancount files in the structure.
* `config/` -- relatively-static "configurations" for the ledger reside in the
  `.beancount` files under this directory. For example, option directives or
  commodity directives can belong to them.
* `quotes/` -- prices of commodities are organized here
  * `FOO/` -- each commodity has its own subdirectory, named after their symbol
    * `main.beancount` -- Each comodity subdirectory has `main.beancount`, which
      include all other .beancount files in the directory.
    * `${YYYYmm}.beancount` -- prices of the commodity are grouped by their
      calendar year and month, and belong to files that are named after the year
      and the month.
* `transactions/` -- individual transactions are recorded under this directory
  * `Assets/`
    * `Foo/Bar/Baz/` -- each account in the ledger can have its corresponding
      subdirectory, named after the acount name. For example, the account
      `Assets:Foo:Bar:Baz` would have this subdirectory path.
      Not all accounts necessarily have its subdirectory. It has the one only if
      Beansprout (or the user) wants to record transactions on the account.
      * `main.beancount` -- Each subdirectory of account has `main.beancount`,
        which include all other .beancount files in the directory.
      * `${YYYYmm}.beancount` -- transactions are grouped by their calendar year
        and month.
  * `Liabilities/`
  * `Equity/`
  * `Expenses/`
  * `Income/` -- Other kinds of accounts have similar structure.
* `.beansprout.beancount` -- This is a special file that stores `custom`
  directives that configure beansprout's behavior. It is not included in the
  primary ledger file.

# Configuration

Beansprout supports several configurations under the `beansprout` custom
directive.

## Importers
Beansprout dynamically load and instantiate importers as defined in the
`custom` directive. Here is the syntax of the directive:

```beancount
DATE "custom" "beansprout" "importer" "IMPORTER_MODULE_NAME" "KEY1" "VALUE1" "KEY2" "VALUE2" ...
```

* `IMPORTER_MODULE_NAME` is the name of the Python module that exports
  `Importer` class. It should be importable from Python's import path.
* `KEY1`, `VALUE1`, `KEY2`, `VALUE2`, ... are key-value pairs that are passed
  to the constructor of the `Importer` class.


Example:
```beancount
1970-01-01 custom "beansprout" "importer" "soysprout.importers.moneyforward" "wallet_account" "Assets:Cash:Wallet" "expected_institution" "財布" "expense_accounts_path" "mapping/moneyforward/expense_accounts.tsv" "income_accounts_path" "mapping/moneyforward/income_accounts.tsv"
```
