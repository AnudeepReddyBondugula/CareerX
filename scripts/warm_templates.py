#!/usr/bin/env python
"""Compile every bundled template once.

Run at image build time for two reasons: it populates Tectonic's package cache
so the first real request does not pay for a multi-minute package download, and
it fails the build if a template does not typeset.
"""

from __future__ import annotations

import sys

from careerx.examples import example_profile
from careerx.latex import LatexCompiler
from careerx.renderers import ResumeRenderer


def main() -> int:
    renderer = ResumeRenderer()
    compiler = LatexCompiler(assets_dir=renderer.assets_dir, timeout_seconds=900)

    if compiler.engine is None:
        print("No LaTeX engine available; nothing to warm.", file=sys.stderr)
        return 1

    profile = example_profile()

    for template in renderer.available_templates():
        result = compiler.compile(renderer.render(resume=profile, template=template), job_name=template)
        print(f"{template}: {len(result.pdf_bytes)} bytes via {result.engine}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
