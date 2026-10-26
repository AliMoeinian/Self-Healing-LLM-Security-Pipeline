# How I think and What I did

**Project start date:** October 24, 2026 (2026-10-24)

An honest record of my reasoning, the work completed, and the assistance I use during this research exercise. I will update this document as the project progresses, distinguishing plans from implemented and tested work.

## Task 1 — Understanding the exercise

Before starting this exercise, I did not have experience in LLM security. To build an initial understanding, I asked ChatGPT to explain the invitation email and the exercise document, clarify the problem, and break down the work I would need to do.

The discussion helped me understand the proposed **probe → patch → verify** cycle: test a model for security weaknesses, apply mitigation mechanisms, and repeat the tests to evaluate their effect. It also clarified the expected deliverables: a reproducible implementation, a short technical report, and a short slide deck.

**Assistance used:** ChatGPT helped interpret the requirements and outline possible steps. It also drafted this entry and the initial README at my request.

**Status:** Initial requirements clarification only. No pipeline code has been implemented, no security experiments have been run, and no mitigation results are available yet. The explanation provides a starting point; it does not establish that any proposed approach works.

## Task 2 — Reading about Garak directly

I started reading about Garak and began reading the paper myself, rather than asking an AI tool to summarize it for me. My aim is to build my own understanding of the tool and its approach before making implementation decisions.

The sources I am using for this reading stage are:

- **Paper:** https://arxiv.org/pdf/2406.11036
- **GitHub repository:** https://github.com/NVIDIA/garak
- **Documentation:** https://docs.garak.ai/garak

Once I have worked through these sources, I plan to return to the professor's requirements and use what I have learned to guide the next steps of the exercise. I will record any additional searches or sources here as I use them.

**Assistance used:** ChatGPT drafted this progress entry from my account of what I started doing. I am reading the paper directly; this entry does not report an AI-generated summary of it.

**Status:** Reading in progress. This entry records the start of that work, not completion of all three sources or any implementation or experimental results.

## Task 3 — From reading to a scoped research plan

**Date:** October 26, 2026 (2026-10-26)

Since the previous entry, I have read the Garak paper myself and developed an overall understanding of what Garak does and how its probing and evaluation workflow operates. This does not mean that I have implemented an integration or validated every feature of the framework.

The exercise gives me room to define a bounded problem rather than implement every suggested component. I proposed studying privacy in calendar scheduling: assistants coordinate a meeting, while a malicious participant tries to extract private calendar details through their conversation.

I had already come across **CalBench: Evaluating Coordination–Privacy Trade-offs in Multi-Agent LLMs** before this planning discussion. Its private-calendar coordination setting provided inspiration for framing my idea:

- **CalBench paper:** https://arxiv.org/abs/2605.09823
- **Version consulted in this discussion:** https://arxiv.org/pdf/2605.09823v3

The calendar scenario and the direction I wanted to explore came from me. I then used ChatGPT to discuss the idea, examine the supplied paper, and refine the research question, threat model, metrics, and seven-step plan below. The project is my own exercise and proposed adaptation, informed by prior work and this discussion; I am not claiming that multi-agent calendar privacy or adversarial agents are new concepts, or that this constitutes an established novel research contribution. CalBench itself also discusses adversarial configurations.

I plan to generate the calendar data ourselves, using entirely fictional people, events, and private details. This is a bounded research exercise intended to demonstrate my reasoning and experimental approach, not a deployment using real personal calendars. Synthetic data will let us control the scheduling constraints and know the correct answers for evaluation.

The intended model family is **Ministral (Mistral)**. The exact model identifiers, number of models, API endpoints, and provider configuration remain to be selected after checking availability, costs, and applicable usage conditions. I will document these decisions as the work progresses.

### Research question

> In a multi-agent meeting-scheduling system, to what extent do input-level and output-level defenses reduce disclosure of private calendar details caused by prompt injection in inter-agent messages, and how do those defenses affect scheduling success?

The evaluation will consider privacy and task completion together. A system that prevents disclosure by refusing every scheduling request would not meet the intended goal.

### Planned steps — not yet implemented

1. **Define the scenario and confidentiality policy.** Use three fictional people, each represented by an assistant with access only to that person's private calendar. The task is to find a common two-hour meeting slot during working hours in the following week, without moving existing events. Sharing availability and candidate slots is permitted; revealing private event titles, categories, descriptions, locations, or associated people is prohibited. This policy concerns event-detail confidentiality, not prevention of every inference about availability.

2. **Fix the attacker model and entry point.** In attack runs, one participant is malicious and controls only its outgoing negotiation messages. It cannot inspect other calendars or modify the other assistants' system instructions or code. Begin with predefined attack messages, including attempts to claim authority or request private details under scheduling pretexts. Treat direct requests for private data separately from instruction-injection attempts. Adaptive attackers and MCP tool-output injection are possible extensions, outside the initial scope.

3. **Generate synthetic scenarios and define evaluation.** Create fictional calendars with and without a valid common slot, retaining ground truth for deterministic scheduling checks. Measure attack success as the fraction of attack runs exposing at least one prohibited detail, scheduling success as a correct valid-slot proposal or correct report that no slot exists, and disruption of benign requests. Inspect all messages visible to the attacker, using explicit matching and a fixed manual-review rubric for paraphrased disclosures. Keep development scenarios separate from final evaluation scenarios.

4. **Select the model and establish a baseline.** Start with one available Ministral model used in separate assistant roles, recording its identifier, API configuration, generation settings, and usage. Run benign and adversarial scenarios before adding mitigations. The baseline still receives the confidentiality instruction, which remains present in every condition. If the attacks do not succeed, report that result rather than weaken the baseline to manufacture a vulnerability.

5. **Evaluate two independently configurable defenses.** Explore an input/prompt defense that reinforces the trust boundary around incoming agent messages and an output defense that restricts outgoing communication to permitted scheduling information. Compare four conditions: baseline, input defense only, output defense only, and both defenses. Develop the defenses on development scenarios and freeze their configuration before final evaluation.

6. **Connect the probe–patch–verify loop through Garak.** Determine the appropriate Garak integration for testing the scheduling system, with scenario-specific probes and disclosure detection where needed. The intended cycle is: probe the system, detect a disclosure, activate a predefined mitigation according to an explicit rule, rerun the evaluation, and compare results. Here, repair means activating a configured defense; it does not mean retraining model weights or automatically generating defense code. Its effectiveness remains an experimental question.

7. **Prepare reproducible artifacts and report limitations.** Record code, configurations, synthetic-data generation settings, model settings, traces, outcomes, and resource usage. Produce the short report and presentation requested in the exercise. Attribute the CalBench-inspired design and distinguish our simplified evaluation from its full benchmark, including its VPS privacy metric, which is not part of the initial plan. Check attribution and license requirements if we later reuse code, data, or prompts. Avoid generalizing results from synthetic scenarios and a limited model selection to real-world security guarantees.

**Assistance used:** I read the Garak paper directly and supplied the calendar-privacy idea and the CalBench reference. ChatGPT helped refine the experimental framing and drafted this record. We will continue documenting assistance and decisions as they occur.

**Status:** Research framing and planning only. The seven steps above are planned work, not completed implementation. No calendar dataset, model integration, attack evaluation, or defense results have been produced yet.
