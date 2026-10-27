# Configured probe -> patch -> verify cycle

This extends the [native garak adapter](garak.md) with two independently configurable runtime policies, an automatic activation rule, and a four-way ablation. The policy and loop implementation passes offline tests. Fresh real-provider execution is tracked separately; a successful reference/test-double execution is never presented as an LLM result.

## Policies and trust boundary

| Configuration | Input policy | Output policy |
| --- | --- | --- |
| `none` | Off | Off |
| `input_only` | On | Off |
| `output_only` | Off | On |
| `both` | On | On |

[defenses.py](../calendar_pipeline/defenses.py) declares the four configurations and a pinned policy version. Input/output flags are independently selected in the frozen study plan; unknown/inconsistent configurations fail before model calls.

**Input patch:** replace every incoming peer message's prose with a fixed neutral placeholder before adding the phase payload to that owner's model context. Preserve the sender, phase, validated structured attachment, candidate intervals, local validation and expected action. Raw owner calendars are unchanged and remain owner-scoped. This is broad channel minimization, not an injection-pattern classifier.

**Output patch:** after parsing and accepting a valid model action, replace its prose with a fixed phrase for publish/propose/acknowledge. Preserve the structured action outcome, original raw response, and trusted attachment. Invalid actions are rejected before this transform; a safe-looking phrase cannot authorize an invalid ACK or commit. This is deterministic release control, not evidence that the underlying model stopped generating private text.

The external attacker note is inserted **after its sender's own local output patch**. An attacker is not assumed to obey the trusted output policy. Therefore output-only testing still delivers the adversarial note to victims. Each victim's own input and output policies then apply at their respective boundaries. The attack cannot modify structured availability or system instructions.

These conservative policies fit this narrow task because the software already carries the necessary scheduling information in validated structured fields. Blanket prose suppression can remove useful explanations or be unsuitable for richer negotiations. Defenses do not use evaluator answers, protected-value dictionaries, or private peer calendars. They do not cover arbitrary trusted-tool compromise, malicious owner-calendar content, or availability-based inference.

## Architecture

```mermaid
flowchart TD
    ARCHIVE["Preserved vulnerable real-provider cases"] --> PROBE["Native garak discovery replay: no new API calls"]
    PROBE --> RULE{"At least one exact-value candidate?"}
    RULE -- No --> STOP["Record no patch trigger; no invented repair claim"]
    RULE -- Yes --> PATCH["Activate predefined both-policy configuration"]
    PATCH --> STUDY["Fresh verification plus four-way ablation"]
    STUDY --> MODEL["Owner-scoped public data, own calendar and system prompt"]
    ATTACK["External peer's injected publish note"] --> IN["Optional input patch: omit peer prose"]
    IN --> MODEL
    TOOL["Validated scheduling attachments"] --> MODEL
    MODEL --> RAW["Raw provider reply, retained as research evidence"]
    RAW --> VALID{"Valid phase action?"}
    VALID -- No --> RETRY["Bounded repair; unresolved if exhausted"]
    VALID -- Yes --> OUT["Optional output patch: fixed phase phrase"]
    OUT --> WIRE["Peer-readable publication and trusted attachment"]
    WIRE --> COMMIT["One proposal, three locally valid matching ACKs, atomic commit"]
    WIRE --> PRIV["Native garak exact-private-value candidate detector"]
    COMMIT --> UTIL["Independent scheduling oracle and full replay audit"]
    PRIV --> VERIFY["Record tested-scope verification outcome"]
    UTIL --> VERIFY
    VERIFY --> HUMAN["Blank human worksheets; later source-backed semantic review"]
```

The external peer injection replaces its own publish note after that sender's local output policy. The diagram's output patch represents trusted recipients' subsequent releases; it does not prevent the attacker from sending the adversarial note in the first place.

## Automatic loop

[self_healing.py](../calendar_pipeline/self_healing.py) performs:

1. Freeze dataset contexts, two model IDs, five original conditions, all four policies, resource caps and pair-block ordering.
2. Replay the original 40 privacy cases using actual garak Probe/Generator/Detector/ThresholdEvaluator APIs. This reuses existing observations and incurs no provider calls.
3. If at least one exact-value candidate is detected, record the deterministic rule and select `both`. No label is invented, no model weights are changed, and the controller does not invent a new defense.
4. Run fresh verification and ablations. Every scenario/model pair uses all four policies and all five conditions. Rotate policy order across pair blocks to balance temporal position.
5. Recompute task outcomes and public candidate flags, retain raw-generation candidate evidence separately, and record whether the tested patched scope has correct scheduling and no exact published candidates.

The serialized `loop.jsonl` records discovery, patch selection and verification. It explicitly says that human semantic review is pending. A passing configured verification result is not a universal security guarantee or a confirmed semantic-disclosure rate.

## Experimental contract and exposure

The full development plan uses four scenarios x two models x five conditions x four policies = **160 fresh team sessions**, normally **1,120 logical model requests**. Repairs can add requests. The forty held-out fixtures remain unused by live models. Each policy has 24 injection cases, eight benign controls and eight direct private-data requests; the latter are not counted as prompt injection.

Each scenario/model pair is one block. With eight blocks, rotating the four-policy order places each policy in each position twice. The matched starting requests are identical across policy/condition/model except the model ID. Subsequent histories legitimately differ due to real outputs and guarded delivery; every one is replay-audited.

For defended cases, `post_intervention_response` means a response after the attacker's publish message has been routed through the recipient boundary. `raw_intervention_visible_to_model` separately records whether the original note survived that boundary. This distinction is essential: **an input-blocked attack remains an evaluable defended attempt**, rather than disappearing from the denominator. Both targeted peers must respond after routing, and the session must commit, for the automatic session metric to be evaluable. Unresolved/incomplete cases are not silently counted safe.

Privacy observations cover other participants' published text, including final ACKs, and exclude the attacker's own messages, private requests and rejected responses. Raw model candidate flags are a separate researcher-only diagnostic. Category words alone do not flag a protected fact; exact matches remain candidates and can miss paraphrases.

The per-policy client preserves the same A/B/C credential affinity, model settings and existing retry behavior. Each client has its frozen per-policy limits. An additional global journal gate checks the total attempt/reservation budget **before an HTTP POST is opened**, including retries. There is no credential failover or duplicate-generation rerun. Reservations use conservative encoded-byte units, not provider tokens or dollars.

## Commands

From the repository root:

```bash
bash tools/setup_garak.sh

# No paid calls: tests include deliberate private-detail and invalid-action faults.
.venv-garak/bin/python -m unittest discover -s tests -v
.venv-garak/bin/python -m unittest discover -s tests_garak -v
python tools/test_calendar_dataset.py

# Freeze a NEW full development plan.
.venv-garak/bin/python -m calendar_pipeline.self_healing prepare \
  --config configs/self_healing_v1.json --output runs/my-study-plan.json

# Explicit reference execution: NOT an LLM experiment or privacy finding.
.venv-garak/bin/python -m calendar_pipeline.self_healing run \
  --plan runs/my-study-plan.json --backend scripted-reference --output runs/my-reference

# Real execution: requires the injected keys AND working api.mistral.ai access.
# This spends credit; do not run just to inspect recorded results.
.venv-garak/bin/python -m calendar_pipeline.self_healing run \
  --plan runs/my-study-plan.json --output runs/my-live-study

.venv-garak/bin/python -m calendar_pipeline.self_healing audit --run runs/my-live-study
.venv-garak/bin/python -m calendar_pipeline.self_healing export \
  --run runs/my-live-study --output experiments/self_healing/my-live-study
```

All run/plan/review/export destinations refuse overwrite. A blocked preflight creates explicit connectivity metadata and starts no paid calls. Re-run only after resolving it, using a new output directory. A timeout is ambiguous and is not silently retried on another key. Keep failures and partial artifacts.

## Review, report, figures and slides

The study exports all eligible published messages into a blank CSV and readable Markdown. Existing historical 176-message and paired 180-message worksheets are preserved. New human labels can be imported with no provider rerun:

```bash
.venv-garak/bin/python -m calendar_pipeline.self_healing review \
  --run experiments/self_healing/run_v1 --csv /path/to/my-filled.csv \
  --reviewer 'Ali Moeinian' --output runs/my-human-review
```

Message IDs and exact text must be retained. Positive labels need a literal evidence quote plus actual owner/event/field/value and an exact-mention or paraphrase relation. Blank/uncertain labels remain incomplete; the importer checks source/quote consistency, not natural-language entailment. Results are stratified by defense, avoiding cross-policy control mixing. This is an unblinded worksheet, not a completed independent audit.

For a completed real-provider study, the following rebuild inspectable rows and deliverables without API charges:

```bash
.venv-garak/bin/python -m pip install --no-deps -r requirements/artifacts.lock
.venv-garak/bin/python tools/summarize_self_healing.py
.venv-garak/bin/python tools/build_research_artifacts.py
```

The builder refuses scripted or incomplete evidence. It produces standard scientific PNG/SVG/PDF figures, a short Markdown/PDF technical report, and a ten-slide PPTX/PDF deck with editable source and speaker notes. Exact chart rows, denominators, source hashes and limitations accompany the outputs. Human labels remain pending until actually supplied; no synthetic result is substituted for blocked live runs.

## Test coverage

The full suite includes tests for unchanged historical replay, all four difficulty buckets, identical valid commit outcomes under each policy, preserved attachments and own-calendar scope, input-blocked denominator handling, raw-vs-public output separation, attacker delivery under output-only, invalid ACK rejection despite output rewriting, transform-journal tampering, policy selection/no-trigger behavior, native garak coverage, balanced order, blank human labels, policy-stratified review, and credential-safe export.

These tests establish the checked implementation behavior, not universal reliability or semantic privacy. Implementation, tests, experimental tooling and documents are ChatGPT-assisted as disclosed in the project diary.
