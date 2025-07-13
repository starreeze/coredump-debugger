import sys

from .core_dump import load_core_dump
from .interface import debug_core_dump

if __name__ == "__main__":
    if len(sys.argv) == 2:
        dump = load_core_dump(sys.argv[1])
        debug_core_dump(dump)
    else:
        print("Usage: python -m dpdb <dump_file>")
        sys.exit(1)
