#!/usr/bin/env python3
"""Wrapper for the bean-format command."""

import sys
from beancount.scripts.format import main

if __name__ == "__main__":
    sys.exit(main())
