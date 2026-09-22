"""Compatibility launcher for the installed standalone macOS app."""

import subprocess
import sys


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("The SafeSet desktop app is available on macOS only.")
    try:
        result = subprocess.run(
            ["/usr/bin/open", "-b", "org.ozyjay.SafeSet"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise SystemExit("Install SafeSet.app before launching the desktop.") from None
    if result.returncode != 0:
        raise SystemExit("Install SafeSet.app before launching the desktop.")


if __name__ == "__main__":
    main()
