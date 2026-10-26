# Recorded benign integration pilots

The experiment plans, actual Mistral responses, paired-input audits, and negative scheduling outcomes are retained here. The data are synthetic. Credential values and Authorization headers are absent.

## Results

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

## Interpretation and next step

Connectivity, controlled data delivery, trace reconstruction, and the evaluator have been exercised. **A successful autonomous scheduling baseline with these models has not yet been demonstrated.** Do not proceed as if attack-induced task failures can already be isolated from benign coordination failures.

The next development step is a more explicit proposal/acknowledgment protocol, with local validity checks and a clear rule for reaching a common decision. Any such change must receive a new version, use development fixtures, preserve both models' paired inputs, and retain the current negative results. A structured calendar protocol or additional allowed-information tools must be documented as application design rather than claimed as model reasoning or security improvement. No further paid tuning was performed after these two pilots and the copy diagnostic.
