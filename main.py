#!/usr/bin/env python3
"""
Back-compatible entry point.

The project is now the installable `sermonflow` package with a `sermonflow`
console script, but `python main.py "John 17"` -- how the proof of concept was
run -- still works. It just forwards to sermonflow.cli.
"""

from sermonflow.cli import main

if __name__ == "__main__":
    main()
