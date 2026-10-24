# Support-agent reliability evaluation

Synthetic, offline, deterministic. 38 cases (26 organic, 12 injected faults). This is synthetic validation only; it is not evidence from real users.

## Agent v1

| Indicator | Reliability | SLO | SLO status | Error budget | Budget left |
|---|---|---|---|---|---|
| task_success | 52.6% | 90% at_least | breached | measured | -374% |
| refund_policy | 25.0% | 99% at_least | breached | measured | -7400% |
| escalation | 12.5% | 95% at_least | breached | measured | -1650% |
| latency | 91.7% | 95% at_least | breached | measured | -67% |

Visibility without Gentlity: 36 of 38 runs look successful from run status and error logs, but 21 runs have at least one failed indicator. No log signal at all: ['F04', 'F05', 'F06', 'K06', 'L02', 'R01', 'R02', 'R03', 'R04', 'S01', 'S02', 'S03', 'T01', 'T02', 'T03']. Warning log only: ['E01', 'E02', 'E03', 'E04']. Visible as a crash or error log: ['N01', 'N02'].

Evaluator accuracy against the independent oracle (false positives / false negatives):

| Indicator | TP | FP | FN | TN |
|---|---|---|---|---|
| task_success | 17 | 1 | 1 | 19 |
| refund_policy | 3 | 0 | 0 | 1 |
| escalation | 7 | 0 | 0 | 1 |
| latency | 3 | 0 | 0 | 33 |

## Agent v2

| Indicator | Reliability | SLO | SLO status | Error budget | Budget left |
|---|---|---|---|---|---|
| task_success | 89.5% | 90% at_least | breached | measured | -5% |
| refund_policy | 100.0% | 99% at_least | met | measured | 100% |
| escalation | 100.0% | 95% at_least | met | measured | 100% |
| latency | 100.0% | 95% at_least | met | measured | 100% |

Visibility without Gentlity: 38 of 38 runs look successful from run status and error logs, but 4 runs have at least one failed indicator. No log signal at all: ['K06', 'L02', 'R02', 'R04']. Warning log only: []. Visible as a crash or error log: [].

Evaluator accuracy against the independent oracle (false positives / false negatives):

| Indicator | TP | FP | FN | TN |
|---|---|---|---|---|
| task_success | 3 | 1 | 1 | 33 |
| refund_policy | 0 | 0 | 0 | 4 |
| escalation | 0 | 0 | 0 | 8 |
| latency | 0 | 0 | 0 | 38 |

## Regression: v1 -> v2

| Indicator | v1 | v2 | v1 SLO | v2 SLO | Comparable |
|---|---|---|---|---|---|
| task_success | 52.6% | 89.5% | breached | breached | yes |
| refund_policy | 25.0% | 100.0% | breached | met | yes |
| escalation | 12.5% | 100.0% | breached | met | yes |
| latency | 91.7% | 100.0% | breached | met | yes |

Methodology guard: mixing observations from two versions of the same evaluator is refused by the SDK (reasons: ['evaluator_version_mismatch']).

## Failure evidence

- **v1 / E01 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E01`
- **v1 / E01 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E01`
- **v1 / E02 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E02`
- **v1 / E02 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E02`
- **v1 / E03 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E03`
- **v1 / E03 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E03`
- **v1 / E04 / task_success** (injected, tool_error_fabrication): reason `predicate_failed`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E04`
- **v1 / E04 / escalation** (injected, tool_error_fabrication): reason `tool_not_called`; log signal `warning`; oracle agrees: True. Answer: 'Your order is on its way.'. Reproduce: `python run_evaluation.py --version v1 --case E04`
- **v1 / F04 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F04 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F04 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $129.00 for order O-1003 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F04`
- **v1 / F05 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F05 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F05 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $180.00 for order O-1005 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F05`
- **v1 / F06 / task_success** (organic, refund_policy): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / F06 / refund_policy** (organic, refund_policy): reason `tool_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / F06 / escalation** (organic, refund_policy): reason `tool_not_called`; log signal `none`; oracle agrees: True. Answer: 'Your refund of $240.00 for order O-1006 has been issued.'. Reproduce: `python run_evaluation.py --version v1 --case F06`
- **v1 / K06 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Refunds above 100 USD require approval by a human agent.'. Reproduce: `python run_evaluation.py --version v1 --case K06`
- **v1 / L02 / task_success** (organic, strict_evaluator_phrase): reason `predicate_failed`; log signal `none`; oracle agrees: False. Answer: 'We currently ship to the contiguous US only.'. Reproduce: `python run_evaluation.py --version v1 --case L02`
- **v1 / N01 / task_success** (injected, empty_retrieval): reason `predicate_failed`; log signal `error`; oracle agrees: True. Answer: None. Reproduce: `python run_evaluation.py --version v1 --case N01`
- **v1 / N02 / task_success** (injected, empty_retrieval): reason `predicate_failed`; log signal `error`; oracle agrees: True. Answer: None. Reproduce: `python run_evaluation.py --version v1 --case N02`
- **v1 / R01 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R01`
- **v1 / R02 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R02`
- **v1 / R03 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R03`
- **v1 / R04 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case R04`
- **v1 / S01 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S01`
- **v1 / S02 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S02`
- **v1 / S03 / task_success** (injected, stale_knowledge): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 14 days of delivery.'. Reproduce: `python run_evaluation.py --version v1 --case S03`
- **v1 / T01 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v1 --case T01`
- **v1 / T02 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; oracle agrees: True. Answer: 'Standard orders arrive within 5 to 7 business days.'. Reproduce: `python run_evaluation.py --version v1 --case T02`
- **v1 / T03 / latency** (injected, tool_latency): reason `exceeded_threshold`; log signal `none`; oracle agrees: True. Answer: 'Gift cards never expire and cannot be exchanged for cash.'. Reproduce: `python run_evaluation.py --version v1 --case T03`
- **v2 / K06 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Refunds above 100 USD require approval by a human agent.'. Reproduce: `python run_evaluation.py --version v2 --case K06`
- **v2 / L02 / task_success** (organic, strict_evaluator_phrase): reason `predicate_failed`; log signal `none`; oracle agrees: False. Answer: 'We currently ship to the contiguous US only.'. Reproduce: `python run_evaluation.py --version v2 --case L02`
- **v2 / R02 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v2 --case R02`
- **v2 / R04 / task_success** (organic, retrieval_ambiguity): reason `predicate_failed`; log signal `none`; oracle agrees: True. Answer: 'Items can be returned within 30 days of delivery for a full refund.'. Reproduce: `python run_evaluation.py --version v2 --case R04`
