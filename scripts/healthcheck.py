#!/usr/bin/env python
"""Container health probe: succeed only if /healthz answers."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

url = f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz"

try:
    with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310 - fixed localhost URL
        sys.exit(0 if response.status == 200 else 1)
except (urllib.error.URLError, OSError) as exc:
    print(f"health check failed: {exc}", file=sys.stderr)
    sys.exit(1)
