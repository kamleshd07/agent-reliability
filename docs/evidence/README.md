# Evidence artifacts

* `test_p29_judge_live.py.txt`: live judge -> HTTP exporter -> real platform tests (scripted
  providers, canary strings with a positive control, P3 summary and P4 SLO values compared with
  hand-computed numbers).
* `test_platform_terminated_tls.py.txt`: platform-terminated TLS scenarios (trusted CA delivers;
  untrusted CA pauses the endpoint and writes nothing). Needs a harness change: `PlatformServer`
  takes `ssl_files=(cert, key)` and passes `ssl_certfile`/`ssl_keyfile` to `uvicorn.Config`, and its
  `base` property uses `https://localhost:<port>` for TLS.
* Neither file belongs to the SDK test suite. They need the P28 SDK-to-platform E2E harness in
  `<workspace>/gentlity-p28-e2e`, which was NOT modified; run them from a
  scratch copy of that workspace: copy the file to `tests/` (drop the `.txt`), apply the harness
  change above for the TLS file, and run
  `E2E_SDK_ROOT=<sdk tree> E2E_PLATFORM_ROOT=<platform tree> E2E_VENV=<venv> scripts/run_e2e.sh <16|17> real -- -q`
  (set `E2E_TMPDIR` to a writable scratch directory). Two assertions in `test_a_delivery.py` and
  `test_i_real_startup.py` check the platform directory name; use the `E2E_PLATFORM_ROOT` basename.
* Results recorded 2026-10-17: 84 tests passed on PostgreSQL 16.15 and 17.11 with the final SDK and
  final platform (80 existing scenarios + 2 judge + 2 platform-terminated TLS).
