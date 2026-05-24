#!/usr/bin/env python3
"""Debugging plugin that dumps the options map and all directives to stderr.

Intended for development and debugging. Loading this plugin causes the entire
processed directive stream and the options map to be written to stderr, so it
can be used to inspect what other plugins in the pipeline have produced.

Usage:
    plugin "beansprout.plugins.print"
"""

import sys

import beancount

__plugins__ = ("print_txn", )


def print_txn(entries, options_map):
    """Write options_map and every entry to stderr; return entries unchanged."""

    for key, value in options_map.items():
        print(f"{key}: {value}", file=sys.stderr)
    for entry in entries:
        print(beancount.format_entry(entry), file=sys.stderr)

    return entries, []
