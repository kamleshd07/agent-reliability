# P30 independent execution validation

Reviewer: fresh independent validator. Date: 2026-10-22.

## Method and isolation

Read the original Session 3 requirement, repository AGENTS.md, architecture assessment and independent architecture/implementation/security reports. Copied the SDK source into a unique disposable reviewer directory, created independent Python 3.12.15 and 3.13.16 environments, and installed declared development, HTTP, OTel-test and exactly pinned LangChain Core 1.6.13 extras. Tests executed against the copied SDK, not the author's environment. LANGSMITH_TRACING=false and LANGCHAIN_TRACING_V2=false were set for framework execution. Local TLS/HTTP fixtures are exercised by the existing exporter tests; no paid model, hosted ingestion, cloud or proprietary platform mutation occurred.

This validator changes only this reviewer-owned report in the implementation worktree. No merge, tag, release or publication is authorized by this report.

## Independently executed results

| Check | Actual result |
|---|---|
| Python 3.13.16 final full SDK suite | 1,802 passed, 1 skipped; 20.35 seconds |
| Python 3.12.15 full SDK suite before final three regression additions | 1,795 passed, 1 skipped; 19.97 seconds |
| Final instrumentation unit + real pinned-framework integration subset | 61 passed, no skips; 0.22 seconds |
| Existing HTTP exporter, policy, release/review, real TLS, uncertainty, language-neutral protocol and experimental API regressions | 458 passed, no skips; 11.82 seconds |
| Strict mypy | Passed: 72 source files |
| Ruff lint | Passed after author corrections |
| Ruff format | Passed: 303 files |
| Reviewer wheel and sdist build | Passed |
| Complete distributed-artifact verifier | Passed with no stages skipped: metadata/content, base wheel/offline examples, sdist install/quickstart, HTTP-extra mocked delivery, LangChain-extra sync/async and explicit evaluation, OTel-extra example, installed-wheel downstream strict typing |
| Offline benchmark harness smoke (`--iterations 5 --repeats 1`) | Passed; execution/serialization smoke only, not a performance claim |
| Separate clean Python 3.12 no-extra wheel install | Exactly one installed distribution; neutral instrumentation imports do not import LangChain, HTTPX or OTel; sanitized missing-extra ImportError at setup |

The single full-suite skip is existing test `tests.contract.test_p29_wire_conformance::test_p29_s09_ac03_payloads_validate_against_platform_v2_models`. It explicitly requires P29_PLATFORM_ROOT and P29_PLATFORM_PYTHON and is reported NOT_EXERCISED here. It is not a passing platform round trip. This validator did not run Python 3.11; the independent implementation/security reviewers and author's version matrix supply separate evidence for that interpreter.

## Findings and remediation

- **V-1 — MEDIUM — Internal P30 reports shipped in source distribution. CLOSED.** Independent build plus the new artifact guard rejected the source distribution because architecture and internal review reports remained included. The intended pyproject exclusion had not actually been applied. Author added the explicit `/docs/p30` exclusion. This reviewer refreshed the source, rebuilt both artifacts and independently reran the complete artifact verifier successfully. No guard was disabled.
- **V-2 — LOW — New-file quality gate failures. CLOSED.** Initial Ruff found seven unnecessary dict constructors and two overlong comments. Author corrected them; independent lint and strict typing passed. Public-guide Python-block formatting is also independently verified. A subsequently added overlong benchmark-report string was corrected by the author; the final copied tree passes Ruff lint and format (300 files). These are recorded failures rather than claimed passing initial runs.

Independent runtime source manifest: SHA-256 `608e3554306ce8ffc965862606a0ee5c5d1de11eb99591151513f3e779cd8324`, computed from compact, key-sorted JSON mapping all relative `src/agent_reliability/**/*.py` paths to SHA-256 file hashes. This associates execution with runtime content despite later documentation-only changes.

Local disposable evidence directory: `/private/tmp/gentlity-p30-validator-20261022/`. Retained evidence includes `final-full313.xml`, `final-full312.xml`, `full.xml`, `full312.xml`, `exporter.xml`, `final-focused.xml`, build/artifact logs, Ruff/mypy logs and initial/final runtime manifests. Initial packaging and formatting failures remain preserved alongside remediated results.

## Gate and limitations

**Independent validation recommendation: GO for owner review of the additive experimental local-capture vertical slice.** No unresolved actionable validation finding remains. Runtime tests and independent artifact checks support the additive experimental local-capture slice; they do not validate full P30 remote span ingestion, arbitrary framework versions, streaming/batch APIs, maximum production performance or truthfulness of framework callbacks. Detailed traces remain local and automatic execution capture does not manufacture outcome evaluation. Customer aliases and third-party tracing remain separate privacy responsibilities. No unresolved BLOCKER or HIGH validation finding identified. Owner approval, other reviewer gates and required CI remain separate gates. D14 OPEN; Phase B NO-GO.

## Final additions recheck

After three focused regressions and the README link correction were added, this reviewer refreshed the copied repository and independently executed missing-dependency and unsupported-version fresh-process tests, the no-global-patching/tracing-environment lifecycle test and the complete README link contract: **10 passed, 0 skipped, 0 failed** (`final-additions.xml`). Ruff lint and formatting passed again (300 files). Runtime manifest remains exactly `608e3554306ce8ffc965862606a0ee5c5d1de11eb99591151513f3e779cd8324`; these additions do not modify runtime or package configuration. The prior full artifact installation remains applicable to that runtime/configuration; this does not claim a rebuilt final documentation artifact.

The independently repeated complete Python 3.13 suite after these additions passed: **1,798 passed, 1 skipped in 20.40 seconds** (`recheck-full313.xml`). The sole skip is unchanged and identified above. Final independent validation recommendation remains **GO for owner review**, with no unresolved actionable finding; required CI and owner approval remain separate gates.

## Final test-only freeze verification

Independently read and executed the four final signal/termination/sampling regression cases in the refreshed copy. SystemExit and KeyboardInterrupt preserve the exact original exception object, reset SDK context/admission and retain failed execution classification. The disposable subprocess emits RunStarted and then self-terminates with SIGTERM; it emits no fabricated terminal event. Intermediate sampling decisions reproduce across differing input values, independently of values returned by the Runnable. These tests do not promise persistent recovery after termination.

- Complete real-framework integration file: **43 passed, 0 skipped, 0 failed in 0.40 seconds** (`freeze-integration.xml`).
- Complete Python 3.13.16 SDK suite: **1,802 passed, 1 skipped in 20.35 seconds** (`freeze-full313.xml`). The same explicitly identified cross-repository P29 test remains skipped.
- Final Ruff lint passed; format passed for **303 files** (`freeze-ruff.log`, `freeze-format.log`).
- Runtime manifest independently reconfirmed unchanged at `608e3554306ce8ffc965862606a0ee5c5d1de11eb99591151513f3e779cd8324`. These final additions are test/documentation changes, not runtime/packaging changes.

No additional finding. **GO for owner review remains the validation recommendation.** CI and owner merge approval remain independent gates; no release, deployment or production readiness is implied.
