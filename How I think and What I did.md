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

## Task 4 — Building and reviewing the synthetic calendar dataset

**Date:** October 26, 2026 (2026-10-26)

I approved the proposed synthetic-data design and asked ChatGPT to implement the complete 60-scenario fixture, review and refine it, and document its construction. There are 15 scenarios each in the easy, medium, hard, and infeasible classes. Every scenario contains three private calendars and one two-hour meeting request over a fixed five-day working week.

The data are generated by deterministic Python code with recorded seeds, not by asking a model to invent scheduling answers. Semantic event descriptions use a small original template bank composed with ChatGPT assistance. No personal calendar data, external data collection, or live model API calls were used. The design is inspired by CalBench, but its code, event labels, and fixtures were not copied into our dataset.

ChatGPT implemented a separate validator that reconstructs availability from the final event timestamps and exhaustively checks all 65 meeting starts per scenario. The release contains 180 private calendars and 2,334 events; all 3,900 candidate intervals were checked. The dataset has 20 development and 40 evaluation scenarios, with five and ten per class respectively.

During review, the entity vocabularies were separated between calendar owners to reduce ambiguity when distinguishing disclosure of another person's information from an attacker's own information. Suggested first-speaker identities were also balanced instead of making the attacker always speak first. After refinement, 21 acceptance and deliberate-corruption tests passed, including byte-for-byte regeneration of all scenario files and the manifest. This was AI-assisted implementation and review, not an independent human audit.

The [dataset documentation](data/calendar/README.md) explains the generation constraints, field contract, privacy policy, limitations, and exact reproduction/validation commands. The saved validation report and summary CSV document the checked release. In a future runner, public information, each owner's private events, and evaluator-only answers must remain separate.

**Assistance used:** I chose the project direction and approved the data plan. ChatGPT wrote the generator, validator, tests, dataset text templates, and documentation, executed the checks, and refined the artifacts. I do not claim to have manually implemented or independently audited that code.

**Status:** Synthetic dataset construction and automated data validation are complete for this version. Difficulty classes express solution scarcity, not measured model difficulty. Model selection, Garak integration, attacks, defenses, and experiments remain future work; no security effectiveness has been demonstrated.

## Task 5 — Implementing and checking the benign multi-agent baseline

**Date:** October 26, 2026 (2026-10-26)

I supplied three credentials securely through environment settings and selected exactly two official Mistral-platform models: `ministral-3b-2512` and `ministral-8b-2512`. I asked ChatGPT to implement the baseline, test connectivity and evaluation, and ensure both models receive the same underlying scenario data. Credentials were assigned consistently to roles A, B, and C rather than switched to bypass failures or limits.

ChatGPT implemented frozen experiment plans, owner-scoped model contexts, synchronous message passing, JSON response checks, a Mistral HTTPS client, request/response journals, token accounting, deterministic request replay, and independent scheduling scores. Both models receive the same initial scenario/owner inputs and generation settings; later conversations can differ because they contain the models' actual outputs. The dataset was not regenerated or changed between models. Only four development fixtures were used; held-out scenarios were not used for prompt tuning.

An initial proxy connection failure was diagnosed separately from credentials. After network access became available, all three credentials returned HTTP 200 and exposed both model IDs. The first paid pilot completed 72 chat calls but yielded 0/8 correct team outcomes. Five sessions were protocol-valid. Traces showed calendar-arithmetic errors, unsupported availability claims, disagreement, and some final responses missing the required outer envelope.

Rather than change or hide those results, ChatGPT retained them and introduced an explicit v2 protocol. It clarified the response envelope and added deterministic availability computed only from each assistant's own calendar. Raw private events remained available to that assistant; no global answer or other owner's calendar was supplied. The v2 pilot completed another 72 calls with all eight sessions protocol-valid, but scheduling success remained 0/8. This is a development observation, not evidence that the model coordination problem has been solved.

A separate two-call diagnostic asked each model to copy the scenario ID, owner ID, and complete availability list from the same frozen input. Both copies were exact. This checks data delivery in that setting, not scheduling ability. Across the two pilots, all 24 paired first-round request comparisons matched except for model ID, and all 144 scheduling requests passed reconstruction from the frozen plan and actual preceding outputs.

The deterministic reference scheduler passed the full application path separately. The local verification suite passed 32 application/transport tests and the existing 21 dataset tests. These include request contamination, false scheduling decisions, malformed responses, partial runs, credential-safe transport behavior, and artifact export checks. API values were not logged or committed. Actual model traces, usage, protocol versions, and negative outcomes are retained in [the experiment evidence](experiments/README.md).

**Assistance used:** I selected the model family and exact model IDs, supplied the credentials, and requested the implementation and fair-input checks. ChatGPT wrote and executed the runner, tests, diagnostics, and documentation and analyzed the recorded development failures. I do not present this code or its automated review as independently written or audited by me.

**Status:** Connectivity, input integrity, application plumbing, and scoring have been exercised. Correct autonomous team scheduling has not yet been demonstrated with these models and protocols. A clearer proposal/acknowledgment mechanism is the next development need before attributing failures to attacks. No attacks, Garak integration, mitigation evaluation, or privacy-success claims have been made.
