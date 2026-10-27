# Configured repair study

The [implementation guide](../../docs/self_healing.md) documents both independent defenses, their trust boundaries, the native-garak automatic trigger and four-way ablation, exposure semantics, commands, and human review.

The [frozen development plan](../self_healing_plan_v1.json) specifies 160 fresh team sessions: four scenarios, two models, five conditions, and four policy configurations. The 40 held-out fixtures are not included. The original discovery replay reuses the earlier real-provider privacy cases and makes no new model calls.

## Execution status

**Initial live preflight blocked by the environment proxy. No paid request started in that attempt.** The saved connectivity metadata records three network/proxy failures. An unauthenticated diagnosis returned `Tunnel connection failed: 403 Forbidden`, before reaching Mistral. The network draft includes api.mistral.ai but requires environment Publish; turn-level network permission alone did not resolve the proxy refusal. This is not evidence that the Mistral credentials are invalid.

Offline validation passed 94 application/privacy/protocol/defense tests, 21 optional garak/self-healing tests, and 21 dataset tests (**136 total**). An explicit scripted-reference study also completed and was audited; it is a software test, not live model evidence or a measured privacy-defense success rate. The report builder refuses incomplete or scripted results rather than substituting them for the planned live comparison.

The fresh real-provider study and its result artifacts will be recorded here once connectivity is available. Until then, no before/after live counts or human-confirmed rates are asserted.
