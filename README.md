# Self-Healing LLM Security Pipeline

> A small research prototype exploring a **probe → patch → verify** feedback loop for LLM security.

## The idea

Use [Garak](https://github.com/NVIDIA/garak) to probe a language model for security weaknesses, apply configurable input/prompt and output defenses, and repeat the evaluation to measure what changed.

The focus is on clear reasoning, reproducible experiments, and honest reporting of results and limitations.

## Project status

**Dataset prepared.** A reproducible synthetic calendar dataset is available: 60 scenarios, 180 private calendars, and independently checked scheduling answers. Model experiments and the Garak pipeline have not started; there are no attack or defense results yet.

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
| [Synthetic calendar dataset](data/calendar/README.md) | Data, generation method, privacy boundaries, and validation instructions |
| [LICENSE](LICENSE) | Project license |

Dataset checks run with Python's standard library:

```bash
python tools/validate_calendar_dataset.py
python -m unittest discover -s tools -p 'test_calendar_dataset.py' -v
```

Model setup, experiment configurations, and results will be added as the pipeline is implemented and validated.
