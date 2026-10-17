"""Verify vendored P28 hashes, optionally against a read-only platform checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-root", type=Path)
    arguments = parser.parse_args()
    fixtures = ROOT / "tests" / "fixtures" / "p28"
    manifest = json.loads((fixtures / "manifest.json").read_text())
    for name, entry in manifest.items():
        data = (fixtures / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"vendored fixture hash mismatch: {name}")
        parsed = json.loads(data)
        for key in ("fixture_format_version", "wire_version"):
            if parsed[key] != entry[key]:
                raise SystemExit(f"fixture version mismatch: {name}")
        if arguments.platform_root:
            published = (
                arguments.platform_root / "docs/roadmap/P28/reference-vectors" / name
            )
            if published.read_bytes() != data:
                raise SystemExit(f"platform fixture drift: {name}")
    print(
        f"{len(manifest)} fixture hashes verified; "
        f"platform comparison: {bool(arguments.platform_root)}"
    )


if __name__ == "__main__":
    main()
