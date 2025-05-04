#!/usr/bin/env python3
"""Wrapper for the bean-doctor command."""

import sys
from beancount.scripts.doctor import main

if __name__ == "__main__":
    sys.exit(main())
