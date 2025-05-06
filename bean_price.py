#!/usr/bin/env python3
"""Wrapper for the bean-price command."""

import sys
from beanprice.price import main as beanprice_main


def main():
    """Entry point for the bean-price command."""
    return beanprice_main()


if __name__ == "__main__":
    sys.exit(main())
