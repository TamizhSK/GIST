"""`python -m yeet`. Guarded, because a bare `main()` here runs the whole CLI
the moment anything walks the package — pkgutil, import-linter, a docs builder.
"""

from yeet.cli.app import main

if __name__ == "__main__":
    main()
