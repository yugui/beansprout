#!/usr/bin/env python3
"""Wrapper for the bean-check command."""

import sys
from beancount.scripts.check import main as beancount_main


def main():
    """Entry point for the bean-check command."""
    return beancount_main()


if __name__ == "__main__":
    sys.exit(main())
