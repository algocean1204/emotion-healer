"""healer 명령어 진입점."""

from __future__ import annotations

import sys

USAGE = "사용법: healer run"


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "run":
        from app.cli.run import run

        run()
        return
    print(USAGE)
    sys.exit(1)
