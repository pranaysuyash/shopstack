"""Entry point so ``python -m shopstack.cli`` works."""
from shopstack.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
