#!/usr/bin/env python3
"""The only hook the rails plugin registers. See rails/dispatch.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from rails.dispatch import main
except Exception as exc:  # noqa: BLE001 — never block a tool call because the package broke
    sys.stdout.write(
        '{"systemMessage": "RAILS: plugin package failed to import (%s); every rails gate is unguarded"}'
        % type(exc).__name__
    )
    sys.exit(0)

sys.exit(main(sys.argv))
