"""CLI entrypoint for source-map v2.

Usage:
    python -m source_map_v2 --target ./src --output .cc-rsg/source-map.json

Mirrors the v1 source-map.py flags so it can be swapped in. Warnings about
unsupported languages are printed to stderr (loud, never silent).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import DEFAULT_EXCLUDES, build_source_map


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="cc-rsg source-map v2 (role-typed, framework-aware)")
    p.add_argument("--target", type=Path, required=True, help="target source root")
    p.add_argument("--output", type=Path, default=None, help="output JSON path (default: stdout)")
    p.add_argument("--exclude-globs", default=None,
                   help="comma-separated extra excludes (added to defaults)")
    args = p.parse_args(argv)

    if not args.target.exists():
        print(f"ERROR: target does not exist: {args.target}", file=sys.stderr)
        return 2

    excludes = list(DEFAULT_EXCLUDES)
    if args.exclude_globs:
        excludes.extend(g.strip() for g in args.exclude_globs.split(",") if g.strip())

    smap = build_source_map(args.target, excludes)
    payload = smap.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        stats = payload["stats"]
        print(
            f"source-map v2: {stats['units_total']} units from {stats['files_scanned']} files "
            f"(excluded {stats['files_excluded']}). Written to {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    for w in payload["warnings"]:
        print(f"WARNING: {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
