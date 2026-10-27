# Technical report and data provenance

- [Preparation report, PDF](preparation_report.pdf) / [Markdown](preparation_report.md): four pages explaining framing, data, diagnosis, actual prior results, implemented defenses, planned comparison, limits and research extensions.
- [Structured report source](preparation_report_source.json) and [chart rows](preparation_chart_rows.csv).
- [Preparation artifact/source fingerprints](preparation_manifest.json).

The current report is explicitly **preparation-stage**: fresh live defense results and independent human confirmation are pending. No unexecuted value is represented as zero. This is a reviewable discussion draft, not a completed human-confirmed defense evaluation.

The report/PDF and [ten-slide deck](../slides/README.md) use the same actual historical findings and scope limitations. PDF fonts are embedded. Code, document and figure preparation is ChatGPT-assisted as disclosed in the diary.

`tools/prepare_discussion_artifacts.py` rebuilds these preparation files without API calls. After a completed audited real-provider study, `tools/build_research_artifacts.py` generates the separate `technical_report.md/.pdf`, final comparison figures and `artifact_manifest.json`. Its source gate rejects incomplete or scripted results before writing research result rows.
