"""Allow running the preembed CLI with ``python -m preembed``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
