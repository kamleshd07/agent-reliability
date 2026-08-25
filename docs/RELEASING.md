# Releasing Agent Reliability

This is the maintainer procedure. It publishes nothing automatically and
requires no private infrastructure for local verification.

## Preconditions

1. Work from an reviewed commit on the release branch with a clean tree.
2. Confirm GitHub private vulnerability reporting is enabled or another real
   private channel is documented in `SECURITY.md`.
3. Confirm ownership/availability of the `agent-reliability` PyPI project.
4. Prefer PyPI Trusted Publishing from a protected GitHub environment. Do not
   store long-lived PyPI tokens in the repository.

## Prepare and verify

1. Run `ruff check .`, `ruff format --check .`, `mypy src`, and
   `python -m pytest --cov --cov-report=term-missing`.
2. Confirm CI passes on Python 3.11, 3.12, and 3.13.
3. Run focused M3/M4/M5 and compatibility/security suites.
4. Set `agent_reliability.__version__` to the intended version. Hatch reads
   package metadata from that single source. For final GA, also remove
   "pre-GA" from the package description and set the Development Status
   classifier to `5 - Production/Stable` in the same reviewed release commit.
5. Move relevant changelog content from Unreleased to the version heading;
   add the real release date only when cutting the release.
6. Remove old artifacts, then run `python -m build`.
7. Run `python scripts/verify_release_artifacts.py` to inspect and smoke-test
   wheel, sdist, typing, base-without-OTel, and OTel-extra installations.
8. Confirm filenames are exactly
   `agent_reliability-<version>-py3-none-any.whl` and
   `agent_reliability-<version>.tar.gz`.

## Optional release candidate

For the first GA, publish `1.0.0rc1` to TestPyPI or PyPI, install it into a
fresh environment, rerun the canonical example, and solicit downstream
validation. Do not claim the final release date during the RC.

## Tag and publish

1. Merge the reviewed release commit; require all branch-protection checks.
2. Create an annotated `v<version>` tag from that exact commit and push it.
3. Build artifacts once in the trusted release workflow; do not rebuild them
   separately for each destination.
4. Publish through PyPI Trusted Publishing with environment protection and
   artifact provenance enabled. Signing/provenance should use the publisher's
   identity mechanism; no signing secret belongs in the repository.
5. Create the GitHub release from the same tag and attach the exact artifacts.

## Post-publication verification

In a new environment, run:

```bash
python -m pip install --no-deps agent-reliability==<version>
python -c "import agent_reliability; print(agent_reliability.__version__)"
python -m pip install "agent-reliability[otel]==<version>"
```

Run the canonical quickstart against the published wheel, compare the printed
version to the tag and PyPI metadata, and verify hashes/provenance on both
artifacts. If verification fails, stop promotion and publish a corrected
release under a new version; never replace an existing PyPI file.
