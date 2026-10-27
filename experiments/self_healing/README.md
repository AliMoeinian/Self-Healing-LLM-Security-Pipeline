# Configured repair study

The [implementation guide](../../docs/self_healing.md) documents both independent defenses, their trust boundaries, the native-garak automatic trigger and four-way ablation, exposure semantics, commands, and human review.

The [frozen development plan](../self_healing_plan_v1.json) specifies 160 fresh team sessions: four scenarios, two models, five conditions, and four policy configurations. The 40 held-out fixtures are not included. The original discovery replay reuses the earlier real-provider privacy cases and makes no new model calls.

## Execution status

**Initial live preflight blocked by the environment proxy. No paid request started in that attempt.** The saved connectivity metadata records three network/proxy failures. An unauthenticated diagnosis returned `Tunnel connection failed: 403 Forbidden`, before reaching Mistral. The network draft includes api.mistral.ai but requires environment Publish; turn-level network permission alone did not resolve the proxy refusal. This is not evidence that the Mistral credentials are invalid.

Offline validation passed 94 application/privacy/protocol/defense tests, 21 optional garak/self-healing tests, and 21 dataset tests (**136 total**). An explicit scripted-reference study also completed and was audited; it is a software test, not live model evidence or a measured privacy-defense success rate. The report builder refuses incomplete or scripted results rather than substituting them for the planned live comparison.

The fresh real-provider study and its result artifacts will be recorded here once connectivity is available. Until then, no before/after live counts or human-confirmed rates are asserted.

## Ready up to final API execution

The user subsequently asked to advance everything up to the final API calls while connectivity is unresolved. The [preparation report](../../reports/preparation_report.pdf), [ten-slide PDF](../../slides/preparation.pdf), [PowerPoint](../../slides/preparation.pptx), and [real-source figures](../../figures/README.md) are now available. They use actual prior observations and clearly leave the fresh defense comparison pending.

Five optional artifact/readiness tests also pass, bringing the total to **141**. The local readiness check confirms the 160-session plan, normally 1,120 logical completions, package versions, and presence of the three variables without displaying their values. It does not contact Mistral or validate the keys against the provider.

```bash
# No API call:
.venv-garak/bin/python tools/finalize_study.py --dry-run

# After connectivity is restored: paid run, audit, export, and final deliverables.
.venv-garak/bin/python tools/finalize_study.py
```

The final builder rejects nonreal or partial runs before writing research rows. Raw model generations, published text, blocked-input exposure, and candidate/utility metrics remain separate. No human label is fabricated and no report is called a completed defense evaluation before the live study runs.
