# Support-agent reliability evaluation

Synthetic, offline, deterministic. 38 cases (26 without an injected fault, 12 with one). The agent, its defects and the dataset are written by the SDK authors: this is synthetic validation only, not evidence from real users or about your agent.

## Agent v1

| Indicator | Reliability | n considered | SLO | SLO status | Error budget | Budget left |
|---|---|---|---|---|---|---|
| task_success | 52.6% | 38 | 90% at_least | breached | measured | -374% |
| refund_policy | 25.0% | 4 (small sample) | 99% at_least | breached | measured | -7400% |
| escalation | 12.5% | 8 (small sample) | 95% at_least | breached | measured | -1650% |
| latency | 91.7% | 36 | 95% at_least | breached | measured | -67% |

Small samples (fewer than 10 considered observations) make an SLO verdict or a large negative budget anecdotal: one case moves the percentage a lot.

Illustrative visibility. Baseline = run status plus the example agent's own WARNING/ERROR log lines (not metrics, traces or alerts). 36 of 38 runs look successful on that baseline, yet 20 runs have a confirmed failed indicator. No WARNING/ERROR line at all: ['F04', 'F05', 'F06', 'K06', 'R01', 'R02', 'R03', 'R04', 'S01', 'S02', 'S03', 'T01', 'T02', 'T03']. Warning line only: ['E01', 'E02', 'E03', 'E04']. Visible as a crash or error line: ['N01', 'N02']. Excluded as known text-matching false positives: ['L02']. What counts as visible depends on which log lines this example agent was written to emit.

Text matching versus the agent's structured claims, `task_success` only (false positive = flagged but the structured claim says correct; false negative = passed but wrong). The other indicators read the same state the check would, so no accuracy is claimed for them:

| Indicator | TP | FP | FN | TN |
|---|---|---|---|---|
| task_success | 17 | 1 | 1 | 19 |

## Agent v2

| Indicator | Reliability | n considered | SLO | SLO status | Error budget | Budget left |
|---|---|---|---|---|---|---|
| task_success | 89.5% | 38 | 90% at_least | breached | measured | -5% |
| refund_policy | 100.0% | 4 (small sample) | 99% at_least | met | measured | 100% |
| escalation | 100.0% | 8 (small sample) | 95% at_least | met | measured | 100% |
| latency | 100.0% | 38 | 95% at_least | met | measured | 100% |

Small samples (fewer than 10 considered observations) make an SLO verdict or a large negative budget anecdotal: one case moves the percentage a lot.

Illustrative visibility. Baseline = run status plus the example agent's own WARNING/ERROR log lines (not metrics, traces or alerts). 38 of 38 runs look successful on that baseline, yet 3 runs have a confirmed failed indicator. No WARNING/ERROR line at all: ['K06', 'R02', 'R04']. Warning line only: []. Visible as a crash or error line: []. Excluded as known text-matching false positives: ['L02']. What counts as visible depends on which log lines this example agent was written to emit.

Text matching versus the agent's structured claims, `task_success` only (false positive = flagged but the structured claim says correct; false negative = passed but wrong). The other indicators read the same state the check would, so no accuracy is claimed for them:

| Indicator | TP | FP | FN | TN |
|---|---|---|---|---|
| task_success | 3 | 1 | 1 | 33 |

## Regression: v1 -> v2

By construction v2 fixes what v1 gets wrong; this table shows how the SDK reports such a change, not that v2 is a good agent.

| Indicator | v1 | v2 | v1 SLO | v2 SLO | Comparable |
|---|---|---|---|---|---|
| task_success | 52.6% | 89.5% | breached | breached | yes |
| refund_policy | 25.0% | 100.0% | breached | met | yes |
| escalation | 12.5% | 100.0% | breached | met | yes |
| latency | 91.7% | 100.0% | breached | met | yes |

Methodology guard: mixing observations from two versions of the same evaluator is refused by the SDK (reasons: ['evaluator_version_mismatch']).

## Failure evidence

The report stores the synthetic request and answer text so that you can read each failure. That is this example's choice; the SDK itself does not capture payloads.

- **v1 / E01 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; structured claim agrees it failed: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E01`
- **v1 / E01 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; structured claim agrees it failed: None. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E01`
- **v1 / E02 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; structured claim agrees it failed: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E02`
- **v1 / E02 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; structured claim agrees it failed: None. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E02`
- **v1 / E03 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; structured claim agrees it failed: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E03`
- **v1 / E03 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; structured claim agrees it failed: None. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E03`
- **v1 / E04 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; structured claim agrees it failed: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E04`
- **v1 / E04 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; structured claim agrees it failed: None. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E04`
- **v1 / F04 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F04 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F04 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F05 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F05 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F05 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F06 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / F06 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / F06 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; structured claim agrees it failed: None. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / K06 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Refunds above 100 USD require approval by a human agent.'. Reproduce: `python run_evaluation.py --version v1 --case K06`
- **v1 / L02 / task_success** (organic, strict_evaluator_phrase): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: False. Answer: 'We currently ship to the contiguous US only.'. Reproduce: `python run_evaluation.py --version v1 --case L02`
- **v1 / N01 / task_success** (injected, empty_retrieval): reason `predicate_failed`; log signal `error`; structured claim agrees it failed: True. Answer: None. Reproduce: `python run_evaluation.py --version v1 --case N01`
- **v1 / N02 / task_success** (injected, empty_retrieval): reason `predicate_failed`; log signal `error`; structured claim agrees it failed: True. Answer: None. Reproduce: `python run_evaluation.py --version v1 --case N02`
- **v1 / R01 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R01`
- **v1 / R02 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R02`
- **v1 / R03 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R03`
- **v1 / R04 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R04`
- **v1 / S01 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S01`
- **v1 / S02 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S02`
- **v1 / S03 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S03`
- **v1 / T01 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; structured claim agrees it failed: None. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case T01`
- **v1 / T02 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; structured claim agrees it failed: None. Answer: 'Standard orders arrive within 5 to 7 business days.'. Reproduce: `python run_evaluation.py --version v1 --case T02`
- **v1 / T03 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; structured claim agrees it failed: None. Answer: 'Gift cards never expire and cannot be exchanged for cash.'. Reproduce: `python run_evaluation.py --version v1 --case T03`
- **v2 / K06 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Refunds above 100 USD require approval by a human agent.'. Reproduce: `python run_evaluation.py --version v2 --case K06`
- **v2 / L02 / task_success** (organic, strict_evaluator_phrase): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: False. Answer: 'We currently ship to the contiguous US only.'. Reproduce: `python run_evaluation.py --version v2 --case L02`
- **v2 / R02 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v2 --case R02`
- **v2 / R04 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; structured claim agrees it failed: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v2 --case R04`
