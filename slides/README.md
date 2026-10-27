# Technical discussion slides

[PDF](preparation.pdf) · [Editable PowerPoint](preparation.pptx) · [Outline and speaker notes](preparation.md) · [Structured source](preparation_source.json)

Ten slides cover the question, fixed synthetic data, reliability diagnosis, threat model, native garak integration, actual baseline findings, independent channel policies, and the frozen final-study plan. The deck explicitly marks fresh defense execution and human review as pending. The PowerPoint contains speaker notes; the PDF uses the same authored content with embedded fonts.

The existing 40-case replay and separate 10-case live smoke are not added together as independent copies of one experiment. No blank defense metric is plotted as zero. Test-only clients and synthetic layout checks do not appear as research findings.

Rebuild with `tools/prepare_discussion_artifacts.py` after installing the optional artifact lock. After the final real-provider study, `tools/build_research_artifacts.py` generates a separate `presentation.pptx/.pdf/.md` and source with actual before/after results. Human confirmation is not inferred from generating a deck.
