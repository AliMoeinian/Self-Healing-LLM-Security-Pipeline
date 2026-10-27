# Recorded benign integration pilots

The experiment plans, actual Mistral responses, paired-input audits, and negative scheduling outcomes are retained here. The data are synthetic. Credential values and Authorization headers are absent.

The next stage is now recorded separately in [the privacy pilot](privacy/README.md): real message-injection runs, source-grounded AI-assisted review, four observed private-detail disclosures, and blank human-review files. Scheduling and privacy metrics remain separate.

The subsequent [garak integration stage](garak/README.md) adds an audited native-garak replay of those 40 cases and ten new live team executions. Its [architecture and flowchart](../docs/garak.md) explain the custom whole-application adapter, candidate-versus-confirmed scoring, and importing later human labels without another API run.

## Current result: reliable v4 baseline

The [aggregated v4 report](reliable_baseline_summary.json) re-evaluates two disjoint real-provider batches: the four-fixture [pilot](results/mistral-pilot-v4/summary.json) and the [remaining 16 development fixtures](results/mistral-v4-additional-development/summary.json). Together they cover **all 20 development scenarios, once per model**. No held-out fixture was run against a model.

| Development bucket | Scenarios | `ministral-3b-2512` correct teams | `ministral-8b-2512` correct teams |
| --- | --- | --- | --- |
| Easy | 5 | 5/5 | 5/5 |
| Medium | 5 | 5/5 | 5/5 |
| Hard | 5 | 5/5 | 5/5 |
| Infeasible | 5 | 5/5 | 5/5 |
| **Total** | **20** | **20/20** | **20/20** |

V4 completed **280 successful model requests** with **zero rejected actions or protocol repairs**. There were 281 HTTP POST attempts: one 429 was retried on the same key and succeeded. All 60 paired owner/scenario starting requests matched across models except model ID. Every later request, accepted attachment, acknowledgment, and commit was reconstructed from the recorded state transitions. Provider-reported successful-response usage was **2,549,254 tokens** (2,530,808 prompt; 18,446 completion); this is not a dollar estimate or an accounting of any provider charge for the rejected HTTP attempt.

The software now computes complete local availability and derives common options from the three published records. Models publish, select an option, and explicitly acknowledge a bound proposal. The controller performs local checks and the unanimous commit. This is **application-assisted model coordination**, not evidence that unaided LLM reasoning solved the calendars. Privacy of the free-text messages has not been evaluated.

The [offline protocol verification](reliable_protocol_validation.json) independently checks all 60 fixtures, 174 valid candidate commits, 15 infeasible-case commits, and 567 owner receipts. The local suite passed **65 application/transport/protocol tests plus 21 dataset tests**, including incomplete records, stale calendars, forged receipts, wrong proposal IDs, partial acknowledgments, rollback, idempotency, malformed outputs, and journal tampering.

### The additional v3 failure and its correction

The first structured-protocol pilot is preserved in [the v3 evidence](results/mistral-pilot-v3/summary.json): **7/8 committed and correct sessions**, 55 model calls, and four rejected responses. One 8B session repeatedly copied long availability structures into its action and hit the output-token limit. Bounded retries ended with **unresolved** status and no booking; it was not labeled infeasible or silently filled with a scripted answer. One other rejected action was recovered within the recorded attempts.

V4 retained the same scheduling state machine and introduced phase-specific strict JSON Schema at the provider boundary, a bounded free-text message field, and a 1,024-token output limit. Runtime semantic checks remain in force. The successful v4 runs are new versioned experiments, not replacements for the v3 failure.

See [the current README](../README.md) for the architecture, data-flow chart, and a real request/proposal/ACK/commit example, and [the detailed protocol](../docs/reliable_baseline.md) for the trust boundary and limits. These results support readiness for the next research stage under this fixed contract; they do not establish zero bugs, real-world scheduling reliability, model superiority, or privacy security.

## Historical v1/v2 results

Each pilot used the same four development fixtures with both requested models. Each session has three assistants, two synchronous discussion rounds, and one final decision. There were no attacks, Garak probes, or semantic output defenses.

| Evidence | v1: raw private calendars | v2: calendars + local availability tool |
| --- | --- | --- |
| Completed sessions | 8/8 | 8/8 |
| Successful chat POSTs | 72/72 | 72/72 |
| HTTP errors/retries | 0/0 | 0/0 |
| First-round cross-model request pairs matching except model ID | 12/12 | 12/12 |
| All recorded requests reconstructed from plan and actual history | Passed | Passed |
| Protocol-valid sessions | 5/8 | 8/8 |
| Correct three-way scheduling outcomes | **0/8** | **0/8** |
| Prompt tokens reported by provider | 224,178 | 319,669 |
| Completion tokens reported by provider | 18,003 | 12,371 |
| Total tokens reported by provider | 242,181 | 332,040 |

For **each model separately**, scheduling success was 0/4 in both pilots. These are four development examples, not a statistically reliable estimate of population performance. There were no skipped sessions or hidden replacement answers. CLI exit code **3** correctly denotes complete execution with task/protocol failures; it is not an installation or connectivity error.

The three supplied credentials each returned HTTP 200 from the official Mistral model-list endpoint and exposed both requested exact model IDs. Subsequent chat responses verified actual completion access for both models and all three role-bound credentials. Connectivity metadata is saved in each result bundle.

Including the two-call copy diagnostic, this work made **146 successful chat POSTs** and recorded **582,034 provider-reported tokens**. Read-only model-list requests are separate. No dollar charge is inferred from these token counts; actual billing should be checked in the provider dashboard.

## What failed and what was checked

V1 traces show inaccurate or incomplete availability descriptions, disagreement on final times, false reports that no slot exists, and some bare decision objects instead of the required full response envelope. No malformed response was silently repaired.

After inspecting those development failures, v2 introduced an explicitly versioned prompt with full final-envelope examples and phase reminders. It also added a deterministic **own-calendar-only** availability tool, including each owner's free intervals and candidate starts. It did not supply peer calendars, a common intersection, or oracle answers. The original private semantic events remained in the context. All 72 v2 responses satisfied the JSON protocol, but the teams still failed to agree correctly: seven sessions ended in disagreement, and one agreed incorrectly that no common slot existed. Some messages announced that they were sharing a list without actually including it; subsequent responses inferred unsupported availability.

The independent saved-run audit verifies the actual request snapshots, source data, initial ownership, phase ordering, and delivery of previous-round messages. First-round requests are identical across models except the model name, while subsequent requests correctly reflect each team's actual outputs. We did not repeatedly rerun until a favorable seed or outcome appeared.

A separate [copy-only diagnostic](results/input_delivery_smoke.json) sent the same frozen owner-A view to both models and asked them to copy the scenario ID, owner ID, and complete local available-start list. **Both copied all requested values exactly.** It used two additional chat calls and is explicitly not a scheduling or privacy result. Its expected answer was computed offline and was not supplied as an answer in the request. Combined with the request audit, this supports data-delivery integrity for the tested inputs; it does not prove universal model attention or reasoning correctness.

## Diagnosis before the next implementation change

**Recorded October 26, 2026, after the v2 pilot.** We examined the saved development traces and checked the scoring rather than immediately adding attacks or repeatedly changing prompts. This is a trace-based diagnosis of the observed executions, not a controlled causal ablation or a general claim about the models.

| Observed failure | Application/protocol limitation exposed | Evidence |
| --- | --- | --- |
| An assistant says it is providing its complete availability but supplies no actual list. | The JSON envelope validator checks syntax and field shape, not whether a free-text message contains the scheduling information needed by peers. Valid JSON does not imply a useful negotiation message. | In [CAL-0007 / 8B](results/mistral-pilot-v2/sessions/CAL-0007__ministral-8b-2512.json), A and B's first-round messages announce a list without including it. |
| Later messages assert peer availability that the peers did not actually provide. | The protocol relies on natural-language interpretation and does not require proposals to cite explicit received availability or obtain local confirmation. The runner preserves these claims; it does not silently correct them. | The same trace contains second-round claims about a common start despite the missing first-round lists. |
| Assistants independently choose different valid intervals. | Two discussion rounds followed by simultaneous independent decisions do not establish a shared commitment. There is no explicit proposal identifier, acknowledgment from all three owners, or commit phase. | The concrete example below shows three individually valid decisions that fail the team-agreement criterion. |
| All assistants agree that no common interval exists when one does. | An empty or incomplete negotiation record can be mistaken for proof of infeasibility. The application has no explicit unresolved state or evidence requirement for a no-slot decision. | [CAL-0016 / 3B](results/mistral-pilot-v2/sessions/CAL-0016__ministral-3b-2512.json) reports no common slot, although the validated fixture has exactly one. |

For the easy CAL-0007 scenario with `ministral-8b-2512`, the final decisions were:

| Assistant | Selected interval on November 3, 2026 (UTC) | Valid against all three calendars? |
| --- | --- | --- |
| A | 14:30–16:30 | Yes |
| B | 10:00–12:00 | Yes |
| C | 14:30–16:30 | Yes |

The team still fails: a meeting must have one shared time across all three calendars. We rechecked both intervals against the fixture's exhaustive oracle. Therefore **0/8 successful teams does not mean that every individual proposed interval was invalid**. In v2, seven session failures were disagreement and one was an agreed false infeasibility report, as recorded in the [summary](results/mistral-pilot-v2/summary.json).

Checks completed before deciding on the next change:

- Confirmed provider access and actual chat responses separately from task correctness.
- Checked paired initial requests and reconstructed every later request from its actual history; no mismatched underlying calendar inputs were found in these audits.
- Independently validated the fixtures and reference answers, and retained the separate passing scripted-reference run as a plumbing check.
- Used the two-call copy diagnostic to confirm exact recovery of the requested input fields in that diagnostic; this does not establish that models use every field correctly during negotiation.
- Preserved both pilots, including the v1-to-v2 change history. The v2 envelope changes resolved the observed protocol-format failures, but did not establish successful coordination.

The proposed next revision is to use explicit scheduling data fields, locally validate proposals against each owner's calendar, and require **one identified proposal → acknowledgments from all three owners → commit of that same interval**. An unresolved negotiation should remain distinct from proven infeasibility. Free-text messages and private event details would still need separate privacy evaluation; a scheduling-protocol improvement is not itself evidence of a security improvement.

**Status:** Diagnosis documented; these proposed coordination changes have not been implemented or tested. Their effectiveness must be checked on development fixtures under a new protocol version, retaining identical starting inputs across models. No new API calls were made to write this diagnosis, and no new attack experiment was started.

## Files

- [v1 plan](baseline_plan.json) and [v2 plan](baseline_plan_v2.json): complete frozen configurations and owner-scoped initial messages.
- [v1 summary](results/mistral-pilot-v1/summary.json) and [v2 summary](results/mistral-pilot-v2/summary.json): separate completeness, protocol validity, task correctness, and token usage.
- `results/mistral-pilot-v*/sessions/`: all model requests and normalized responses, with call IDs and hashes.
- `results/mistral-pilot-v*/journal.jsonl`: chronological logical requests, HTTP-attempt metadata, usage, and actual responses. No raw Authorization headers or provider error bodies are captured.
- `results/mistral-pilot-v*/pairing_audit.json`: paired-request checks and usage by model/credential-variable label.
- `results/mistral-pilot-v*/metadata.json`: source-file hashes and UTC run start time. Code evolved from v1 to v2; the original v1 system prompt is retained so both plans remain reconstructible.

Artifact export re-evaluates the run and scans files for the three credential values injected at export time. This is a practical credential check, not a claim that arbitrary artifacts cannot contain secrets. Full synthetic-calendar traces are published intentionally for reproducibility.

## Re-evaluate without API calls

From the repository root:

```bash
python -m calendar_pipeline evaluate --run experiments/results/mistral-pilot-v1
python -m calendar_pipeline evaluate --run experiments/results/mistral-pilot-v2
```

Both currently exit **3**, because the recorded scheduling outcomes failed. Inspect their JSON summaries; do not replace this exit code with a passing status. Re-evaluation requires the matching dataset and supported protocol implementation. It performs no network requests and spends no credits.

The deterministic scripted-reference scheduler separately passes all eight sessions in each protocol, using only own-calendar availability and received peer messages. It demonstrates the fixture and application path can produce and score valid outcomes; its successes are **not** substituted for these model results. Local application tests also deliberately inject wrong decisions, request contamination, partial runs, and transport failures.

## Interpretation and next step at the v2 stage

Connectivity, controlled data delivery, trace reconstruction, and the evaluator have been exercised. **A successful autonomous scheduling baseline with these models has not yet been demonstrated.** Do not proceed as if attack-induced task failures can already be isolated from benign coordination failures.

At that stage, the next development step was a more explicit proposal/acknowledgment protocol, with local validity checks and a clear rule for reaching a common decision. The v3/v4 revisions and additional paid executions are now documented above. They preserve versioned plans and the earlier negative results. Scheduling-protocol improvements are documented as application design rather than claimed as model reasoning or security improvement.
