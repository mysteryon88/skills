import sys
from mutationlib.processes import guard

if __name__ == '__main__':
    raise SystemExit(guard(sys.argv[1]))
