# Self-Healing LLM Security Pipeline

> A small research prototype exploring a **probe → patch → verify** feedback loop for LLM security.

## The idea

Use [Garak](https://github.com/NVIDIA/garak) to probe a language model for security weaknesses, apply configurable input/prompt and output defenses, and repeat the evaluation to measure what changed.

The focus is on clear reasoning, reproducible experiments, and honest reporting of results and limitations.

## Project status

**Benign integration tested.** The synthetic dataset and a versioned three-assistant runner are implemented. Official Mistral access and paired-input integrity were verified for `ministral-3b-2512` and `ministral-8b-2512`. Both recorded pilots completed, but neither achieved a correct team scheduling outcome on the four development scenarios. [Results and limitations](experiments/README.md) are retained; attacks, Garak integration, and defenses have not started.

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
| [Baseline workflow](docs/baseline.md) | Three-agent protocol, frozen model inputs, API configuration, and execution commands |
| [Pilot evidence](experiments/README.md) | Actual requests, responses, input audits, usage, and negative model outcomes |
| [LICENSE](LICENSE) | Project license |

Dataset checks run with Python's standard library:

```bash
python tools/validate_calendar_dataset.py
python -m unittest discover -s tools -p 'test_calendar_dataset.py' -v
python -m unittest discover -s tests -v
```

Python 3.11+ is sufficient; no third-party packages are required. See the baseline workflow for paid API execution. API keys belong in environment settings and are never committed.
