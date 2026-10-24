# Self-Healing LLM Security Pipeline

> A small research prototype exploring a **probe → patch → verify** feedback loop for LLM security.

## The idea

Use [Garak](https://github.com/NVIDIA/garak) to probe a language model for security weaknesses, apply configurable input/prompt and output defenses, and repeat the evaluation to measure what changed.

The focus is on clear reasoning, reproducible experiments, and honest reporting of results and limitations.

## Project status

**Early planning.** The exercise requirements have been reviewed. Implementation and experiments have not started; there are no results or runnable pipeline yet.

## Planned workflow

1. Define a focused threat scenario and evaluation criteria.
2. Run a baseline scan without defenses.
3. Add prompt/input and output mitigations.
4. Repeat the scan and compare outcomes.
5. Document findings, limitations, and possible research extensions.

## In this repository

| File | Purpose |
| --- | --- |
| [Research exercise](Research%20%20Excercise%20CSL.docx) | Original exercise brief |
| [How I think and What I did](How%20I%20think%20and%20What%20I%20did.md) | Reasoning, progress, and disclosure of assistance used |
| [LICENSE](LICENSE) | Project license |

Setup instructions, experiment configurations, and results will be added as the work is implemented and validated.
