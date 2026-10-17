# P29 pilot safeguards SG-1 to SG-6: requirements, SDK evidence, procedures, status

Status: **all six safeguards are NOT SATISFIED for pilot use.** Each is a condition of the
owner's P29-D09 approval ("mandatory before pilot use"); every one of them is defined in terms
of a pilot's configuration, report or operation, which does not exist. Evidence below shows
what the SDK enforces and demonstrates locally; it does not satisfy a pilot condition. No
customer pilot has been started or authorized.

Requirement text is quoted or condensed (meaning preserved) from the owner decision record (P29 Owner Decisions 001, section 4).
Roles are described, not assigned: **no person holds any of them**.

| ID | Requirement (owner record) | SDK-side enforcement / reproducible evidence | Remaining condition and procedure | Responsible role (unassigned) | Status |
|---|---|---|---|---|---|
| SG-1 | Generous pilot budgets and limits: token/cost budgets, `max_pending` and `max_concurrency` sized so budget exhaustion and overload (R13/R14) do not occur in the pilot; any occurrence is reported as a pilot incident, not normal operation | `JudgeLimits`, `JudgeBudget`/`BudgetTracker`, safe documented defaults; exhaustion and shedding are failures with evidence, never verdicts (`test_budget_exhaustion_is_visible_in_observer_coverage_and_failure_evidence`, `test_overload_shedding_is_a_failure_with_evidence_never_a_verdict`, `test_sg1_defaults_are_documented_safe_not_fast_values`) | Size budgets from the pilot's measured traffic (template A below); record every R13/R14 occurrence as an incident; the pilot report states zero or lists them | Pilot owner; application operations owner | NOT SATISFIED |
| SG-2 | Pilot runbook note: one judge failure sets run health `UNAVAILABLE`, which changes `measurement_state` for every indicator in the scope and window | stated in `docs/EVALUATE.md` and `docs/P29_PILOT_RUNBOOK.md` (checked by `test_s00_s12_docs`); behaviour tested (`test_one_failure_marks_the_whole_run_unavailable_via_the_recorder`) and shown against a real platform (local E2E, section "Local platform evidence") | The pilot report must restate the note (template B). A document in the repository is not a pilot report | Pilot owner | NOT SATISFIED (process gate) |
| SG-3 | Read failure rate (and UNKNOWN rate) beside reliability for every judge indicator, in the pilot report and in any dashboard built on P3 | `CoverageReport`/`IndicatorCoverage.describe()` offers no single "healthy" value (`test_coverage_report_offers_no_single_healthy_boolean`, `test_ninety_nine_failures_plus_one_pass_cannot_look_healthy`, `test_attempted_counts_failures_but_determinate_does_not`); the platform's P3 summary returns pass, fail, unknown, execution-failure and health counts together (local E2E) | The pilot report and any dashboard must show the same figures from P3 reads (template C) | Pilot owner; dashboard owner | NOT SATISFIED (SDK part satisfied locally) |
| SG-4 | Deterministic-indicator isolation recommendation: SLOs/gates that must stay readable on deterministic indicators should not be interpreted from `measurement_state` while judge indicators share their scope and window; the pilot evaluates whether judge evaluation can be bound to a separate scope. No new platform feature is proposed | SDK supports a separate scope and run for judge evaluation (`test_a_separate_scope_and_run_keeps_the_other_run_healthy`) | The pilot must evaluate and record whether a separate scope is feasible (template D) | Pilot owner; platform operator | NOT SATISFIED (process gate) |
| SG-5 | Monitor observer reports: the application wires `JudgeObserver` counters (failed by class, shed, skipped) to its own alerting; platform reads are the second line | `JudgeObserver`, `coverage()` counters; observer exceptions are suppressed and counted (`test_p29_s05_ac07_observer_exceptions_are_suppressed_and_counted`) | The application must wire the counters to alerting and show a firing test (template E) | Application operations owner (customer) | NOT SATISFIED (customer wiring) |
| SG-6 | Deliberate `on_no_data`: set explicitly (BLOCK where an outage must stop deployment) and document that partial outage is not covered | documented in `docs/EVALUATE.md` section 3 and the runbook | The pilot gate must set `on_no_data` explicitly and the pilot report must state that partial outage is not covered (template F) | Pilot owner; platform operator | NOT SATISFIED (platform configuration) |

An SG may be marked SATISFIED only when its remaining condition is evidenced by a pilot
artifact (a filled template plus the platform/application evidence it cites) and signed off by
the responsible role once such a role is assigned.

## Reproducible SDK evidence

`python scripts/p29_sg_evidence.py --json OUT.json` runs the tests mapped above and writes one
record per safeguard (test ids, results, Python version). It proves only the SDK-side column.

## Pilot report template and consistency check

`docs/P29_PILOT_REPORT_TEMPLATE.json` is the machine-readable form of templates A-F below. Every
safeguard ships as `NOT_SATISFIED` with empty fields, no evidence and no sign-off.
`python scripts/p29_pilot_report_check.py REPORT.json` refuses a report that marks a safeguard
`SATISFIED` unless every field is present, correctly typed and non-blank (counts positive where a
size is required, text not whitespace, booleans real booleans), at least one evidence reference of
six or more characters, and a sign-off with role, name and an ISO date from 2020 on; it also rejects
duplicate JSON keys and NaN, refuses `pilot_authorized: true` unless all six are satisfied, and reports
`pilot_ready` only when all six are satisfied and consistent. It checks completeness and plausibility of form, not truth: it
cannot verify that evidence exists or that a sign-off is genuine, and it never changes a status.

## Operational checklists (per safeguard, completed by the responsible role during a pilot)

* **SG-1** - measure real traffic first; set `JudgeBudget`, `max_pending`, `max_concurrency` from it;
  run a short soak and confirm `coverage()` shows no budget exhaustion or shedding; record any
  R13/R14 event as an incident; fill template A.
* **SG-2** - copy the SG-2 note into the pilot report and into the runbook the operators use; fill
  template B. Also record the platform fact below: the P7 gate does not read measurement health.
* **SG-3** - take the figures from the platform's P3 summary read (not from the SDK object); show
  pass, fail, unknown, execution failures, determinate and reliability together; fill template C.
* **SG-4** - decide whether judge evaluation can run in its own scope; list the SLOs and gates that
  must stay on deterministic indicators; fill template D.
* **SG-5** - wire the `JudgeObserver` counters (failed by class, shed, skipped, observer errors) to
  the application's alerting; trigger a test alert; record rule ids and result; fill template E.
* **SG-6** - set `on_no_data` explicitly on every gate condition that reads a judge indicator; state
  that a partial outage is not covered; fill template F.

Platform behaviour relevant to these safeguards, pinned by
`tests/integration/test_postgres_judge_indicator_coverage_gate.py` in the platform tree (real
PostgreSQL, hand-computed expectations): `unknown` results and judge execution failures never enter
the reliability denominator; an indicator with only such results has no data, so a P5 policy on it
is `no_data` and the gate applies the condition's `on_no_data`; an SLO's `measurement_state` shows
`unavailable` when a run reported unavailable health, but the P7 gate consumes only coverage and
policy facts, so measurement health does not by itself block or warn. The owner accepted these semantics
for the pilot on 2026-10-17 (decision OD-10); changing them would need a design cycle.

## Local platform evidence (not a pilot)

On 2026-10-17 a scripted-provider judge was run through the HTTP exporter against the
integrated platform on PostgreSQL 16 and 17 in a disposable local environment; the platform's
P3 summary and P4 SLO evaluation were read back and compared with hand-computed values (see
the final completion report). That demonstrates SG-2/SG-3 behaviour on a real platform build;
it is not a pilot, uses no real model and no customer content, and satisfies no SG.

## Templates for the pilot report (fill during a pilot; none is filled here)

**A. SG-1 budget sizing.** Expected evaluations per hour: __; tokens per evaluation (measured):
__; budget per window: __; `max_pending`: __; `max_concurrency`: __; R13/R14 incidents (count and
dates): __; sign-off (role, name, date): __.
**B. SG-2 note.** "A single judge failure sets the run's measurement health to UNAVAILABLE and
changes `measurement_state` for every indicator in that scope and window." Restated in this
report: yes/no; sign-off: __.
**C. SG-3 table.** Per judge indicator and window: pass __, fail __, unknown __, execution
failures __, determinate __, reliability __ (shown only beside the other columns), source (P3
read URL/time): __; dashboards inspected: __.
**D. SG-4 isolation.** Judge indicators share scope with deterministic ones: yes/no; separate
scope feasible: yes/no (reason); decision: __; SLO/gate readings that must stay on deterministic
indicators: __.
**E. SG-5 alerting.** Counters wired (failed by class, shed, skipped, observer errors): __;
alert rule ids: __; firing test date/result: __.
**F. SG-6 gate.** Gate id: __; `on_no_data` value: __; partial outage not covered, stated: yes/no.

Calibration is a separate pilot prerequisite (P29-D10): use the calibration case/report schemas
shipped in `agent_reliability.experimental.judge`; no accuracy or calibration claim is made for the
reference rubrics, and none is made here.
