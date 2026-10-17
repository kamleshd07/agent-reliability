# P28 SDK exporter owner decision record

Approver: Project owner. Date: 2026-10-16.
Provenance: Owner confirmation relayed through ChatGPT. Signature: None.
Scope: P28 SDK HTTP exporter.
Status: Approved recommendations and proposed initial operating values,
subject to documented compatibility and validation conditions.

This SDK-local record supplements the platform approval package without
modifying platform files or historical review reports. The attached owner
instruction for this session is the approval source; no named role or
cryptographic signature is inferred.

## Recorded settings

| Item | Approved starting setting |
|---|---|
| E3 | 1,024 terminal tombstones; 600-second TTL |
| E4 | 50 closure-reserve records; 3 MiB reserved bytes |
| E6 | Configurable provider timeout, initially 60 seconds |
| E7 | Response body at most 65,536 bytes |
| E9 | Connect/read/write/pool 5/30/10/5 seconds; 10 connections; 2 workers |
| E10 | Minimum credential refresh interval 60 seconds |
| E11 | 1,000 diagnostic entries, 24-hour TTL, redacted |

The proposed 1,000-record/4 MiB queue leaves 950 records/1 MiB available to
ordinary records. A maximum 64 KiB record fits both ordinary headroom and the
closure reserve; 50 such records would need 3.125 MiB, so the 3 MiB reserve
does not guarantee 50 maximum-sized records. Both limits apply independently;
the first exhausted limit rejects admission. Architecture 14.4 explicitly
does not promise lossless closure admission. These settings are consistent
with that rule and must not be advertised as guaranteeing 50 closures.

## Recorded policy directions

- Adopt final reviewed D01–D06, D08–D11 and D13 where later decisions do not
  supersede them; keep the core dependency-free and HTTPX optional.
- A: explicit proxy/CA only, system trust by default, TLS verification on,
  ambient environment discovery off; never follow redirects.
- A-https-1: strict eight-step HTTPS syntax validation; transport must verify
  TLS certificates and host identity. Syntax checks alone do not verify peers.
- A2-3: literal loopback only. This is an explicit alternative in Contract
  15.5; base vectors accepting localhost remain unchanged. Test base syntax
  and the selected restriction separately. No hostname plaintext is allowed.
- Preserve PC-2 D1 extensible acknowledgements and D4 distinction between
  event-only conflict and terminal deployment identity mismatch.
- E13/E14: reviewed timer rules and R1 compatibility accounting (no ordinary
  attempt consumed); production retry amplification remains unmeasured.
- J: reviewed recommendation J2; O: O1 unchanged credentials do not resume;
  P: P1 body validation, including 64 nested levels below the top-level object
  and 1,000-character number tokens. N: recommended vendored fixtures with
  hashes; R: recommended discriminator exclusion, preserving v1 bytes.

## Choices still requiring owner selection

- E12: the final contract requires an **approved** UUID version but does not
  choose one. Package E12 offers v4 or v7. Recommendation for selection: v4,
  available across all supported Python versions with no new dependency.
- RA: owner asks for strict bounded parsing, which both RA-a and RA-b provide.
  RA-a rejects eleven-character `00000000060`; RA-b accepts it as 60 and
  preserves the permanent `[0-9]+` rule. Recommend RA-b, numeric maximum
  4,294,967,295, checked without integer overflow. Do not rewrite ra-006;
  execute both alternatives with an explicit, documented expected difference.
- L2: recommended direction needs the focused specification below approved.
  It was not a complete approved state machine in revision 16.

## Focused L2 specification proposal — not approved

No new wire fields or server behavior. Proposed SDK-local additions:
`resume_endpoint()` and projected `endpoint_paused` state.

1. First 3xx closes an endpoint gate and holds the triggering record without
   following Location. Other queued/retry-scheduled records become held;
   already running requests complete through the existing response reducer.
2. Proposed threshold N=3 consecutive TLS **verification** failures closes
   the same gate and holds the third record. Earlier failures use existing
   ordinary-transient accounting. Count verification failures in response
   reduction order across workers; a successful verified TLS exchange resets
   the count. Other network failures neither advance nor reset it. This N and
   reset rule require owner selection; they are not implied by E9.
3. Endpoint, auth, schema, deployment and rate gates are independent. Removing
   one never removes another. Terminal ConfigurationFailed still dominates;
   Closing/Closed reject resume. Proposed projection: existing auth/schema/
   deployment projections precede endpoint_paused; endpoint precedes rate.
4. `resume_endpoint()` explicitly removes only the endpoint gate, resets the
   TLS streak, and requeues held records in original enqueue order only when
   all other applicable gates allow dispatch. No automatic probes or URL
   mutation. It is idempotent without the gate. Async method is owner-loop
   only, like the other resume methods.
5. Paused records retain ids/bytes and the absolute 900-second residence
   deadline; active stopwatch behavior follows existing paused-state rules.
   Redirects and certificate-verification failures have no committed evidence
   outcome by themselves and do not independently set may_have_committed;
   prior uncertainty remains sticky. Existing close-deadline cancellation
   and late-result discard rules apply.
6. Tests required: first redirect and no credential forwarding; N-1/N TLS
   failures; streak ordering/reset across two workers; verified HTTP error
   resets; gate overlaps; explicit resume/no-op; repeat failure; residence
   expiry; close/resume race; in-flight late acknowledgement; async ownership;
   redacted diagnostics. Add endpoint state and gate tests to I04/I08 evidence
   without editing frozen platform criteria.

Selecting L1 instead would retain revision-16 behavior (3xx permanent per
record; TLS verification failures retry to exhaustion). It must be an explicit
selection, not an implementation fallback.

## Pilot workload hypothesis and measurement plan

Engineering hypothesis, not owner-approved production SLO: 20 concurrent
runs, 10 records per run, 20 original records/second, median 1 KiB records,
64 KiB boundary records, and outages of 5, 75 and 900 seconds. Exercise mixed
fleets at 0%, 10%, 50% and 100% legacy instances. Measure peak bytes/bindings,
emit latency distribution, closure rejections, request amplification, retry
and pause residence, and two-worker fairness. Report raw measurements before
proposing E1/E2 production acceptance targets; no invented pass threshold.

## Follow-up owner selections, 2026-10-16

Same approver/provenance/signature and SDK scope as above. In this session the
owner explicitly selected **UUID v4 and RA-b**, and separately approved the
**documented L2 proposal above**, including N=3 and its TLS reset rule. The
previously unresolved bullets and proposal text are retained as the record
of what was presented; these selections settle them for implementation.

## Compatibility correction found during self-validation

The proposal's item 5 sentence that redirects do not independently set
`may_have_committed` conflicts with Architecture 17.2's mandatory sticky-marker
invariant. This was an author wording error, not an owner selection to relax
evidence integrity. Under the owner's explicit compatibility condition, retain
the reviewed rule: a sent redirect without a definite platform 4xx rejection
sets the marker; a TLS verification failure before any request write does not.
The implementation retains this rule. All approved L2 gate/recovery transitions
remain as presented; no approval of the conflicting sentence is claimed.

## Closing recovery wording clarification during independent review

The focused L2 proposal's item 3 says Closing/Closed reject resume, while the
inherited Architecture 17.4 R01/R05 permits recovery during Closing before its
deadline. Under the already recorded compatibility condition, the exporter
retains that reviewed Closing recovery, including independent endpoint gate
removal; Closed and terminal ConfigurationFailed still reject resume. This is
an implementation-author compatibility clarification, not a new owner approval
or a change to the wire contract. The original wording above remains historical.
