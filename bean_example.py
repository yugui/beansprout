#!/usr/bin/env python3
"""Wrapper for the bean-example command."""

import sys
from beancount.scripts.example import main

if __name__ == "__main__":
    sys.exit(main())
