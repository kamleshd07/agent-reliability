"""Validate (and optionally replay) a JSON-lines capture of evidence envelopes.

Degraded-fallback helper from the P29 plan (section 5): the capture produced by
``examples/judge_pilot_demo.py`` can be checked offline, and ONLY on explicit
request POSTed to a platform endpoint you operate.

* Default is a dry run: structural validation and counts, no network.
* ``--post ENDPOINT`` sends each line as a JSON body. The endpoint must be
  https (or http on a loopback host). Authentication is a bearer token read
  from ``--token-file``; nothing is read from the environment.
* Never point this at a shared platform or production without explicit
  authorization. It proves nothing about authentication, delivery guarantees or
  platform aggregation, and the repository's own tests only use a loopback stub.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

TOP_LEVEL = {
    "schema_version", "source", "event_id", "producer_run_id",
    "parent_producer_run_id", "deployment_id", "producer_identity",
    "producer_timestamp", "payload",
}  # fmt: skip
KINDS = {
    "run_lifecycle", "evaluation_outcome", "evaluation_execution_failure",
    "measurement_health",
}  # fmt: skip


def load(path: Path) -> list[dict[str, object]]:
    envelopes = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            body = json.loads(line)
        except ValueError:
            raise SystemExit(f"line {number}: not JSON") from None
        if not isinstance(body, dict) or set(body) - TOP_LEVEL:
            raise SystemExit(f"line {number}: unexpected envelope members")
        payload = body.get("payload")
        if body.get("schema_version") != 2 or not isinstance(payload, dict):
            raise SystemExit(f"line {number}: not a schema-v2 envelope")
        if payload.get("kind") not in KINDS:
            raise SystemExit(f"line {number}: unknown payload kind")
        envelopes.append(body)
    return envelopes


def post(endpoint: str, token: str, envelopes: list[dict[str, object]]) -> Counter[str]:
    parts = urlsplit(endpoint)
    loopback = parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise SystemExit("endpoint must be https (http only for loopback)")
    statuses: Counter[str] = Counter()
    for body in envelopes:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                statuses[str(response.status)] += 1
        except urllib.error.HTTPError as err:
            statuses[str(err.code)] += 1
    return statuses


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--post", metavar="ENDPOINT")
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args(argv)
    envelopes = load(args.capture)
    kinds = Counter(str(e["payload"]["kind"]) for e in envelopes)  # type: ignore[index]
    print(f"validated {len(envelopes)} envelopes: {dict(sorted(kinds.items()))}")
    if args.post:
        if args.token_file is None:
            raise SystemExit("--post needs --token-file")
        statuses = post(args.post, args.token_file.read_text().strip(), envelopes)
        print(f"posted: {dict(sorted(statuses.items()))}")
    else:
        print("dry run: nothing was sent")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
