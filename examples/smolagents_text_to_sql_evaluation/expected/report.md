# smolagents text-to-SQL agent: Gentlity reliability evaluation

Local real-world integration, **not** independent external validation. The agent is the upstream `smolagents` 1.26.0 `ToolCallingAgent` with the upstream `sql_engine` tool; the model is a small local model (`qwen2.5-coder:7b`); the questions are authored by the Gentlity authors (one is upstream's own). Model responses were recorded once and are replayed; the agent loop and SQL execution run for real.

## Indicators

| Indicator | Reliability | n | SLO | SLO status | Error budget | Budget left |
|---|---|---|---|---|---|---|
| task_success | 86.1% | 36 | 9/10 | breached | measured | -39% |
| tool_used | 100.0% | 36 | 19/20 | met | measured | 100% |
| tool_execution | 97.2% | 36 | 19/20 | met | measured | 44% |
| latency | 100.0% | 36 | 19/20 | met | measured | 100% |

## Failures behind task_success

5 of 36 runs failed `task_success`. Visible through the upstream agent's own signals (run state, step errors, empty output): []. Silent (state `success`, no step error, plain answer): ['Q15', 'Q16', 'Q33', 'Q34', 'Q36'].

Manual adjudication of the evaluator verdicts: {'true_failure': 3, 'evaluator_false_positive': 1, 'true_pass': 31, 'evaluator_false_negative': 0, 'ambiguous_case': 1, 'unadjudicated': 0}.

| Case | Outcome | Answer | Expected | Upstream-visible | Verdict |
|---|---|---|---|---|---|
| Q01 | pass | Woodrow Wilson | ['Woodrow Wilson'] | False | true_pass |
| Q02 | pass | Alan Payne | ['Alan Payne'] | False | true_pass |
| Q03 | pass | The total price of all receipts is $110.46. | [110.46] | False | true_pass |
| Q04 | pass | The average receipt price is $27.62. | [27.615] | False | true_pass |
| Q05 | pass | There are 4 receipts. | [4] | False | true_pass |
| Q06 | pass | The highest tip amount is $5.43. | [5.43] | False | true_pass |
| Q07 | pass | Woodrow Wilson left the highest tip with $5.43. | ['Woodrow Wilson'] | False | true_pass |
| Q08 | pass | The sum of all tips is 7.87 | [7.87] | False | true_pass |
| Q09 | pass | 23.86 | [23.86] | False | true_pass |
| Q10 | pass | Margaret James | ['Margaret James'] | False | true_pass |
| Q11 | pass | 3 | [3] | False | true_pass |
| Q12 | pass | ['Alex Mason', 'Woodrow Wilson', 'Margaret James'] | ['Alex Mason', 'Woodrow Wilson', 'Margaret James'] | False | true_pass |
| Q13 | pass | Alex Mason | ['Alex Mason'] | False | true_pass |
| Q14 | pass | Alan Payne, Woodrow Wilson, Margaret James | ['Alan Payne', 'Woodrow Wilson', 'Margaret James'] | False | true_pass |
| Q15 | fail | Alan Payne paid $13.26 for his receipt. | [12.06] | False | ambiguous_case |
| Q16 | fail | Woodrow Wilson left a tip of 5.43, which is 10% of his receipt price of 53.43. | [10.16] | False | evaluator_false_positive |
| Q17 | pass | Alex Mason paid a total of $24.10. | [24.1] | False | true_pass |
| Q18 | pass | Alex Mason left the smallest tip. | ['Alex Mason'] | False | true_pass |
| Q19 | pass | 65.49 | [65.49] | False | true_pass |
| Q20 | pass | The difference between the most and the least expensive receipt price is $41.37. | [41.37] | False | true_pass |
| Q21 | pass | Alex Mason | ['Alex Mason'] | False | true_pass |
| Q22 | pass | 2 customers have a first name starting with the letter A. | [2] | False | true_pass |
| Q23 | pass | The average tip is 1.97. | [1.9675] | False | true_pass |
| Q24 | pass | The total amount spent across all receipts including tips is $118.33. | [118.33] | False | true_pass |
| Q25 | pass | ('Alan Payne', 'Alex Mason', 'Margaret James', 'Woodrow Wilson') | ['Alan Payne', 'Alex Mason', 'Margaret James', 'Woodrow Wilson'] | False | true_pass |
| Q26 | pass | Woodrow Wilson left the highest tip as a percentage of their price, with a tip of 10.16%. | ['Woodrow Wilson'] | False | true_pass |
| Q27 | pass | The customers with a receipt number greater than 2 are Woodrow Wilson and Margaret James. | ['Woodrow Wilson', 'Margaret James'] | False | true_pass |
| Q28 | pass | 21 | [21] | False | true_pass |
| Q29 | pass | 2 receipts have a tip greater than 1. | [2] | False | true_pass |
| Q30 | pass | The average price of the receipts that have a tip above 1 is $32.745. | [32.745] | False | true_pass |
| Q31 | pass | Woodrow Wilson paid the most with a total payment of $58.86. | ['Woodrow Wilson'] | False | true_pass |
| Q32 | pass | Woodrow Wilson | ['Woodrow Wilson'] | False | true_pass |
| Q33 | fail | Bob Smith paid $10.50. | [] | False | true_failure |
| Q34 | fail | Woodrow Wilson | [] | False | true_failure |
| Q35 | pass | The receipt with receipt_id 1 was issued to Alan Payne, but the exact date is not availabl | [] | True | true_pass |
| Q36 | fail | The price of receipt number 9 is 12.50. | [] | False | true_failure |
