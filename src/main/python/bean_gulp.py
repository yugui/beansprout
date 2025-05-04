#!/usr/bin/python3

import beangulp

def main():
    importers = []
    hooks = []
    ingest = beangulp.Ingest(importers, hooks)
    ingest()

if __name__ == "__main__":
    main()