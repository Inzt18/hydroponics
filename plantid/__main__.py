"""python -m plantid server|bridge ..."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        from .server import main as server_main

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        server_main()
        return 0

    from .bridge import main as bridge_main

    # default: bridge CLI; allow `python -m plantid bridge --image ...`
    args = sys.argv[1:]
    if args and args[0] == "bridge":
        args = args[1:]
    return bridge_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
