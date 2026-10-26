# Reliable scheduling baseline: v3 and v4

This revision addresses the [diagnosed coordination failures](../experiments/README.md#diagnosis-before-the-next-implementation-change). The models remain `ministral-3b-2512` and `ministral-8b-2512`, and the calendar fixtures are unchanged. The implementation uses only Python's standard library.

**This is a change to application architecture, not evidence that the models learned to solve scheduling.** Deterministic calendar tools establish factual availability and valid common candidates; models issue control actions and write messages; the application requires unanimous acknowledgment before committing. No fixture oracle is used by the runtime scheduler.

## What changed

| Earlier problem | Implemented mechanism |
| --- | --- |
| A message announces an availability list but omits it. | A model's `publish_availability` action invokes its local calendar tool. The complete structured result is attached by the trusted router; the model never has to transcribe the list. Incomplete or modified lists fail endpoint verification. |
| An assistant invents information about a peer. | Scheduling uses structured availability attachments, not free-text claims. The coordinator derives candidate intervals only from the three published attachments. Raw peer calendars are never supplied to it. |
| Independently valid final choices disagree. | One designated coordinator selects a candidate index. The resulting proposal has one content-bound ID. All three assistants must acknowledge that exact proposal; all three local endpoints must validate it. |
| Missing information is treated as proof of no solution. | Candidate computation requires all three complete records. Only an empty intersection of those complete records can produce `no_common_slot`. Incomplete publication, refusal, malformed actions, or outages remain **unresolved**. |
| A failed write leaves only some calendars updated. | The in-process transaction validates all owners before writing, restores all owner states after an injected write failure, and returns the same receipt to all three owners. |

## Roles and information boundaries

`LocalCalendar` receives the public constraints and **one owner's private calendar**. Its interface publishes availability, validates a proposal, issues an acknowledgment receipt, and records a commit. The same fixed UTC/half-hour/two-hour/five-working-day contract as the dataset is enforced at this boundary; unsupported contracts and invalid initial event intervals are rejected explicitly.

The coordinator receives only published availability and protocol receipts. Complete availability is intentionally shareable under this exercise's privacy policy. The coordinator computes the intersection of that permitted information; it does not inspect private event titles, descriptions, categories, people, or locations, and it does not load reference answers. The offline evaluator reads the oracle **after execution**, as before.

Each model still receives its own raw private event details. Its free-text messages are preserved and sent to peers after the control action is accepted. They are not semantically redacted. Therefore the later privacy-injection experiment remains meaningful: correctly scheduled meetings do not establish that messages protected event details.

The router and local calendar endpoints are trusted application code. Message origin comes from the runner's role assignment, not a sender name asserted inside model text. Content hashes bind records to the request and proposal; they are **not digital signatures** and do not establish security against a compromised router, server, or filesystem.

## Protocol

1. **Publish, three model calls.** Every assistant returns `{"message":"...","action":{"type":"publish_availability"}}`. The router attaches the complete local tool record with owner ID, request ID, calendar revision, and available starts. Publication is synchronous: initial requests contain no other assistant's current-round output.
2. **Propose, one model call.** The first owner in the fixed speaker order is the coordinator. It receives the three availability attachments, peer messages, and an exhaustive candidate list computed from those attachments. Its `candidate_index` selects one option. If and only if the complete intersection is empty, the index is null. The application builds one proposal with its decision, record references, and proposal ID.
3. **Acknowledge, three model calls.** Each assistant receives that proposal, permitted shared availability, peer messages, and the result of its own local validity check. It returns `{"message":"...","action":{"type":"acknowledge","proposal_id":"..."}}`. An endpoint issues a receipt only for the same proposal and a current locally valid calendar snapshot.
4. **Commit, no model call.** The controller requires all three locally issued acknowledgment receipts. It rechecks calendar revisions and validity, then atomically records the same decision and commit ID for all owners. Repeating the commit is idempotent; missing or inconsistent existing reservations are errors rather than silently accepted success.

There are seven model calls per successful session without repairs. The software does not fill in a missing model acknowledgment, substitute a scripted actor, or commit an unsupported interval. It also does not ask models to invent three independent final times.

For infeasible cases, the same publication/proposal/three-ACK sequence records a common no-slot decision without inserting calendar bookings. For unresolved cases, no commit receipt is issued and no calendar booking is made.

## Output validation and bounded repair

V3 used JSON-object output mode plus runtime validation. Its first real pilot exposed an additional issue: one model copied a long availability structure into the action, exhausted its output budget, and repeated the invalid output. That session failed closed; seven other sessions committed correctly. The failure and all attempts are retained.

V4 uses the same state machine with Mistral's **strict JSON Schema response mode**:

- The envelope has exactly `message` and `action`.
- Every phase has its own action fields and type. Extra properties, such as a copied availability array inside `action`, are not part of the schema.
- Candidate indices are bounded integers when options exist, or null for an empty intersection.
- Acknowledgment IDs have the required 64-character hexadecimal form; runtime validation additionally checks the exact current proposal ID and the issuing endpoint.
- `message` remains ordinary free text, capped at 1,000 characters as an output budget. There is no semantic confidentiality filter.

The API field structure was checked against the official `mistralai` 3.5.0 SDK wheel (`mistralai/client/models/responseformat.py` and `jsonschema.py`) and then exercised through real official-platform requests. The SDK was inspected, not added as a runtime dependency. TLS and artifact verification were not disabled.

Runtime checks remain mandatory even with provider-side schema enforcement. Duplicate keys, wrong action semantics, stale records, nonnormal finish reasons, and replies violating the message budget are rejected. Every rejection is logged. At most three protocol attempts are allowed for one step, with explicit correction feedback and preserved previous responses. A persistent invalid response yields unresolved status; it is never scored as infeasibility or silently converted to a valid action.

These structural and scheduling checks are baseline application reliability controls. Any later privacy defense must be evaluated separately against this baseline and must not claim credit for these existing checks.

## Atomicity and scope

Within this single-process research runner, a commit requires all three distinct owners, the same proposal ID, locally issued receipts, unchanged calendar revisions, and a supported candidate. Writes have rollback on failure. Dataset files are never modified; runtime reservations are kept in the run's owner states and represented by the saved receipts.

This is not a production distributed transaction protocol. It does not claim crash-safe external calendar writes, cross-process locking, Byzantine agreement, or protection against a compromised trusted endpoint. An unavailable API or a model that persistently refuses the protocol can still prevent completion. The guarantee is to **avoid an incorrect or partial commit under the checked contract**, not to guarantee cooperation from every future model response.

## Paired-input and evidence checks

Plans freeze each owner's exact initial context, role order, provider options, dataset hashes, and protocol version. Both models receive the same starting requests except for model ID. Later messages can differ because model messages or candidate choices differ, but replay reconstructs every request from the frozen plan and actual prior outputs.

Re-evaluation also checks:

- full logical-request metadata, including credential-variable labels, against the journal;
- each accepted attachment, rejected action, and commit event against the replayed state transitions;
- HTTP attempt hashes and credential labels against logical requests, and successful-response usage/model metadata against the HTTP journal;
- all three saved owner receipts against the common commit;
- the final outcome against the independently validated dataset oracle.

The older v1/v2 plans and results remain verifiable. Nothing is retroactively reclassified as a success.

## Reproduce

From the repository root:

```bash
# Offline tests and exhaustive protocol/oracle verification.
python -m unittest discover -s tests -v
python -m unittest discover -s tools -p 'test_calendar_dataset.py' -v
python tools/validate_reliable_protocol.py

# Four-scenario paired live pilot; this spends API credits.
python -m calendar_pipeline prepare --config configs/baseline_v4.json --output experiments/baseline_plan_v4.json
python -m calendar_pipeline run --plan experiments/baseline_plan_v4.json --backend mistral --output runs/my-v4-pilot
python -m calendar_pipeline evaluate --run runs/my-v4-pilot

# Remaining 16 development fixtures, disjoint from the pilot; also paid.
python -m calendar_pipeline prepare --config configs/baseline_v4_additional_development.json --output experiments/baseline_plan_v4_additional.json
python -m calendar_pipeline run --plan experiments/baseline_plan_v4_additional.json --backend mistral --output runs/my-v4-development
```

Use fresh run directories. Environment variables remain `MISTRAL_API_KEY`, `MISTRAL_API_KEY2`, and `MISTRAL_API_KEY3`, consistently bound to A/B/C. The same-key HTTP retry/rate-limit rules and credential-safe transport from [the earlier workflow](baseline.md#credentials-network-and-spending-bounds) still apply. V4 uses `max_tokens: 1024`; the additional-development configuration raises the local request/reservation ceilings for its explicitly larger workload. These are bounded local accounting units, not dollar estimates.

The [offline validation report](../experiments/reliable_protocol_validation.json) checks all 60 fixtures, all 174 feasible options, all 15 infeasible cases, 567 owner receipts, and idempotent commit behavior against the independent oracle. Including held-out fixtures here validates deterministic scheduling code; it is not an LLM evaluation or prompt-tuning run. Real model tests use only the 20 development fixtures. Live results and their limitations are recorded in [the experiment evidence](../experiments/README.md).
