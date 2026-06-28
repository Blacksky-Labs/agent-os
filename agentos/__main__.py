"""Entry point so the kernel can run as ``python -m agentos`` and, more
importantly, be compiled to a standalone binary by Nuitka for the macOS app
(``agentos resume skipper ...``). See macos-packaging-plan.md and
clients/build-macos.sh.
"""

from agentos.cli import app

if __name__ == "__main__":
    app()
