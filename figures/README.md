# Research figures

These figures use existing real-provider observations or fixed synthetic fixtures. There is **no plotted fresh defense result** while the planned 160-session live study remains unexecuted. Every chart explicitly labels candidate flags and sample sizes; human semantic confirmation is pending.

| Figure | Source and interpretation |
| --- | --- |
| [Baseline private-value candidates](baseline_privacy.png) | Native garak replay of the original 40 real privacy-pilot cases: 0/8 benign, 0/8 direct, 1/8 forged authority, 3/8 task pretext, 0/8 delimiters. Replay adds no new observations. |
| [Model/condition matrix](baseline_matrix.png) | Same cases, n=4 per cell; not an independent experiment or general model ranking. |
| [Calendar example](calendar_example.png) | Actual synthetic CAL-0052 free/busy schedule, all three owners and five days, UTC. Gold shows its unique valid common interval. This evaluator illustration is never supplied to runtime models. |
| [Configured repair architecture](repair_architecture.png) | Implemented data path and automatic policy-activation rule. Fresh live verification remains pending. |

Each basename also has `.svg` and `.pdf` exports. Chart rows are in [preparation_chart_rows.csv](../reports/preparation_chart_rows.csv); file/source fingerprints are in [preparation_manifest.json](../reports/preparation_manifest.json). Labels retain exact counts and denominators. A zero exact match is not evidence of semantic confidentiality.

Rebuild without API calls:

```bash
.venv-garak/bin/python -m pip install --no-deps -r requirements/artifacts.lock
.venv-garak/bin/python tools/prepare_discussion_artifacts.py
```

After the real final study completes, `tools/build_research_artifacts.py` adds privacy/utility comparisons, model/attack matrices, and a same-response output transformation example when the recorded raw evidence supports one. It refuses pending or scripted study results.
