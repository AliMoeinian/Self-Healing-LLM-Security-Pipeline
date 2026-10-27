"""Discussion-ready preparation artifacts using ONLY existing real observations.

Fresh defense results remain pending. No zero or synthetic value is substituted
for a missing before/after result. This command never accesses a model API.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
import sys
from xml.sax.saxutils import escape

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import ROOT,read_json,save_json,sha_file
from calendar_pipeline.garak_scan import audit_scan
from calendar_pipeline.privacy_experiment import audit_experiment
import tools.build_research_artifacts as b
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors


def build():
    audit_experiment(ROOT/"experiments/privacy/paired_runs")
    audit_scan(ROOT/"experiments/garak/replay_v1",ROOT/"experiments/privacy/paired_runs")
    audit_scan(ROOT/"experiments/garak/live_v1")
    baseline=read_json(ROOT/"experiments/garak/replay_v1/summary.json")
    smoke=read_json(ROOT/"experiments/garak/live_v1/summary.json")
    evidence=read_json(ROOT/"experiments/reliable_baseline_summary.json")
    figures=ROOT/"figures"
    figures.mkdir(exist_ok=True)
    b.figure_setup()
    b.context_figures(figures)
    labels={"benign_control":"Benign\ncontrol","direct_request":"Direct\nrequest","authority_spoofing":"Forged\nauthority","task_pretext":"Task\npretext","role_delimiter":"Role\ndelimiters"}
    groups=baseline["groups"]
    fig,ax=b.plt.subplots(figsize=(10.5,4.8),layout="constrained")
    counts=[g["candidate_flagged_sessions"] for g in groups]
    denoms=[g["sessions"] for g in groups]
    xs=b.np.arange(len(groups))
    ax.bar(xs,counts,color="#2563A0",width=.62)
    ax.set_xticks(xs,[labels[g["condition_id"]] for g in groups])
    ax.set_ylim(0,max(denoms)*1.12)
    ax.set_ylabel("Team sessions with an exact-value candidate")
    ax.set_title("Existing development privacy pilot: public candidate flags",loc="left",fontweight="bold",pad=16)
    ax.grid(axis="y",color="#E2E8F0",linewidth=.6);ax.set_axisbelow(True)
    for x,h,n in zip(xs,counts,denoms):ax.text(x,h+.15,f"{h}/{n}",ha="center",fontweight="bold")
    b.save_figure(fig,figures,"baseline_privacy","Source: existing 40-case native garak replay. These reuse earlier real-provider observations; no new calls. Human semantic confirmation pending.")
    models=["ministral-3b-2512","ministral-8b-2512"]
    conditions=[g["condition_id"] for g in groups]
    rows=[]
    matrix=[]
    for model in models:
        values=[]
        for condition in conditions:
            selected=[r for r in baseline["cases"] if r["model"]==model and r["condition_id"]==condition]
            flags=sum(r["candidate_score"]==1 for r in selected)
            rows.append({"model":model,"condition_id":condition,"sessions":len(selected),"candidate_sessions":flags})
            values.append(flags)
        matrix.append(values)
    fig,ax=b.plt.subplots(figsize=(10.5,4.4),layout="constrained")
    im=ax.imshow(matrix,vmin=0,vmax=4,cmap="Blues",aspect="auto")
    ax.set_xticks(range(5),[labels[c] for c in conditions]);ax.set_yticks(range(2),["Ministral 3B","Ministral 8B"])
    ax.set_title("Existing pilot by model and condition",loc="left",fontweight="bold",pad=16)
    for i in range(2):
        for j in range(5):ax.text(j,i,f"{matrix[i][j]}/4",ha="center",va="center",fontweight="bold",color="#172435")
    fig.colorbar(im,ax=ax,label="Flagged sessions",ticks=range(5),shrink=.8)
    b.save_figure(fig,figures,"baseline_matrix","Source: same 40 recorded cases as baseline_privacy. Four scenarios per model/condition; candidate flags do not establish general model safety rankings.")
    out=ROOT/"reports";out.mkdir(exist_ok=True)
    with (out/"preparation_chart_rows.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    sections=[
      ("Status and research question",["This is a preparation-stage technical report. The scheduling baseline, observed vulnerability evidence, native garak integration, and repair implementation are available. Fresh live defense verification is blocked before any paid call by the environment proxy (CONNECT 403 to api.mistral.ai). No fresh mitigation result is asserted. Human semantic labels are also pending.","Research question: can a Garak-triggered, configurable two-layer channel policy reduce private event-detail publication while preserving structured meeting scheduling by small-model teams? The exercise asks for a probe -> patch -> verify prototype. Our code implements this cycle; completing its new real-provider comparison is the remaining execution step."]),
      ("Synthetic task and acknowledged inspiration",["CalBench inspired the private-calendar coordination setting. Our generator/templates and simplified scheduling code are independently built with disclosed ChatGPT assistance; we did not copy CalBench data or code. There are 60 fixtures (15 easy, medium, hard, infeasible), 180 owner calendars and 2,334 fictional events. Twenty fixtures are development; forty have not been run against live models.","Three owner-scoped assistants schedule one immutable two-hour meeting on a UTC half-hour grid during November 2-6, 2026, 09:00-17:00. Availability may be shared; event titles, descriptions, categories, people and locations are protected. Rescheduling costs and information-theoretic availability leakage are outside this bounded prototype."]),
      ("Architecture and diagnosis",["Deterministic local tools compute complete availability. Models publish an action, one coordinator selects a shared candidate, and three assistants acknowledge one bound proposal ID. The controller validates each local calendar and commits identical receipts atomically. The software computes intersections; we do not claim unaided model scheduling ability.","Earlier v1 and v2 pilots each had 0/8 successful team outcomes. Diagnosis found missing availability content, unsupported peer claims, and independent conflicting final choices. V3 achieved 7/8, with one oversized action left unresolved. V4's strict phase schemas and explicit commit protocol then achieved 40/40 across all twenty development fixtures and both models. Negative runs remain preserved."]),
      ("Observed security evidence and evaluation",["The initial privacy experiment used four development scenarios, two homogeneous three-agent Ministral teams, and five conditions: neutral control, direct private-data request, forged authority, scheduling-task pretext and forged role delimiters. The attacker controls one published free-text note, not structured attachments or native system instructions.","Scheduling remained correct in all 40 privacy-pilot sessions. Initial source-grounded AI review found four private-value disclosures among 24 injection sessions: three consistently describe source events; one exposes real details with wrong owner/conflict attribution. Human confirmation remains pending. The control and direct-request groups each had 0/8 observed disclosures in that pilot.","Native garak replay over the same saved 40 cases flagged four exact-value candidates and made zero new model requests. A separate live garak integration smoke executed ten new sessions on selected CAL-0052: 10/10 correct schedules, one 3B forged-authority candidate among six injection attempts. The smoke is not an unbiased prevalence estimate or evidence of mitigation; no defense was active then.","Task scoring uses independent fixture answers, absent from runtime selection. Request bodies, routed messages, protocol actions, local ACKs and receipts are replay-audited. Privacy flags match normalized private values in post-delivery public messages. Exact matching can miss paraphrases; no flag does not establish semantic privacy. Final published ACKs are observable even without a later attacker-model call. The existing application/dataset suite and new integration tests total 141 passing tests."]),
      ("Two implemented defenses and automatic activation",["Input policy removes peer prose before adding it to the recipient's model context; it retains validated scheduling attachments, routing, candidates and local validation. Output policy replaces accepted reply prose with fixed phase phrases before peer publication, retaining original model text as researcher-only evidence. These are independent, versioned channel-minimization policies, not learned semantic classifiers or novel security defenses.","The external attacker note is injected after its sender's own local output policy, so output-only does not neutralize the attacker before victim exposure. Action validation precedes rewriting: an invalid ACK cannot become a safe-looking successful commit. No defense uses private fact dictionaries, peer calendars or the oracle.","The controller uses actual garak discovery replay; any exact-value candidate activates a predefined both-policy repair. Fresh verification plus input-only/output-only/no-defense ablations follow. This is automatic configured repair activation, not autonomous policy invention or weight updates. Deliberate fault tests verify that inputs blocked by a guard remain attempted/evaluable cases, with raw instruction visibility tracked separately."]),
      ("Frozen final study: awaiting API access",["The ready plan specifies four scenarios x two models x five conditions x four policy configurations = 160 fresh sessions and normally 1,120 logical completions. Within eight scenario/model pair blocks, rotating policy order places each policy in each temporal position twice. Starting requests must match except model ID. Later histories reflect actual responses and policy transforms.","The primary machine comparison will report public exact-value candidate sessions out of 24 injection attempts per configuration, alongside scheduling successes out of 40 team sessions per configuration. Benign/direct-request controls, raw-generation flags, token use, retries, and transformation events remain separate. Missing live values are undefined, not zero. Human-confirmed disclosure rates stay undefined until the applicant reviews the messages.","Both per-policy and study-wide HTTP/reservation caps apply before a POST; credentials remain bound to A/B/C without failover. The first preflight was blocked before Mistral authentication. Registered environment variables do not overcome a proxy rejection. The allowlist draft was saved but reports requires-publish; this does not diagnose invalid keys."]),
      ("Reproducibility and human review",["Use Python 3.12, bash tools/setup_garak.sh, and optional requirements/artifacts.lock. Tests: unittest discover -s tests; unittest discover -s tests_garak; python tools/test_calendar_dataset.py. Historical evidence and current code are in the repository. docs/self_healing.md contains the architecture, flowchart, trust boundaries and commands.","tools/finalize_study.py --dry-run performs local readiness checks without networking or charges. After connectivity is restored, its normal mode runs the frozen study, refuses incomplete results, audits/exports synthetic evidence after secret scanning, and builds the full comparison figures, report and ten-slide deck. Rebuilding from saved completed evidence incurs no API cost.","Human worksheets preserve the original 176 messages, the prior 180 paired messages, and the fifty new smoke messages. New study worksheets will include all public messages, including unflagged ones. Labels and evidence are imported into separate policy-stratified reports without rerunning models. A blank label is not a no-leak verdict; semantic interpretation remains the reviewer's responsibility."]),
      ("Limitations, extensions and assistance",["Only four development fixtures and three fixed injection texts are in the planned security comparison. No live held-out estimate, general model ranking, MCP deployment or adaptive attacker claim is supported. Blanket prose suppression preserves utility only for this structured contract and can eliminate useful explanations in richer tasks. Permitted availability may still enable inference about private events.","Future research could compare selective semantic release with strict minimization, attack trusted-tool/MCP boundaries, introduce adaptive multi-turn attacks, repeat seeds across held-out calendars, and measure both explicit disclosures and availability inference. These require new experiments.","The applicant independently read garak and contributed the calendar-privacy framing and scope decisions. ChatGPT implemented code, probes, tests, experiments, review tools, figures and this document/deck. Prior semantic labels were AI-assisted and await independent human confirmation. Test doubles and preparation-stage layouts are not reported as live model results."]),
      ("References and source evidence",["garak paper: https://arxiv.org/abs/2406.11036 ; implementation: https://github.com/NVIDIA/garak ; documentation: https://docs.garak.ai/garak . CalBench inspiration: https://arxiv.org/abs/2605.09823 .", "Evidence: experiments/reliable_baseline_summary.json; experiments/privacy/paired_privacy_report.json and paired_runs/; experiments/garak/replay_v1/ and live_v1/; experiments/self_healing/preflight_blocked/; frozen experiments/self_healing_plan_v1.json. Source: https://github.com/AliMoeinian/Self-Healing-LLM-Security-Pipeline ."])
    ]
    title="Calendar Privacy Repair Prototype: Preparation Report"
    subtitle="Real baseline evidence; defenses implemented; fresh live comparison and human review pending"
    md=["# "+title,"",subtitle,"", "**This document does not report unexecuted defense results.**",""]
    for heading,paras in sections:
        md += ["## "+heading,""]
        for para in paras:md += [para,""]
    md += ["![Actual baseline candidates](../figures/baseline_privacy.png)","", "![Synthetic calendars](../figures/calendar_example.png)","", "![Implemented repair architecture](../figures/repair_architecture.png)",""]
    (out/"preparation_report.md").write_text("\n".join(md))
    styles=getSampleStyleSheet()
    for s in styles.byName.values():
        if hasattr(s,"fontName"):s.fontName="ResearchSans-Bold" if "Bold" in s.fontName else "ResearchSans"
    styles.add(ParagraphStyle("PrepBody",fontName="ResearchSans",fontSize=10,leading=14,spaceAfter=9))
    story=[Paragraph(escape(title),styles["Title"]),Paragraph(escape(subtitle),styles["PrepBody"]),Spacer(1,12)]
    for heading,paras in sections:
        story.append(Paragraph(escape(heading),styles["Heading2"]))
        story.extend(Paragraph(escape(p),styles["PrepBody"]) for p in paras)
        if heading in ("Observed security evidence and evaluation","Two implemented defenses and automatic activation"):
            name="baseline_privacy" if heading.startswith("Observed") else "repair_architecture"
            from PIL import Image as PILImage
            path=figures/(name+".png");w,h=b.image_size(path)
            story += [Image(str(path),width=470,height=470*h/w),Spacer(1,12)]
    def footer(c,doc):
        c.setFont("ResearchSans",8);c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(42,24,"Preparation report | Fresh defense scan and human review pending")
        c.drawRightString(A4[0]-42,24,str(doc.page))
    SimpleDocTemplate(str(out/"preparation_report.pdf"),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=38,bottomMargin=42,title=title,author="AI-assisted research prototype").build(story,onFirstPage=footer,onLaterPages=footer)
    save_json(out/"preparation_report_source.json",{"title":title,"subtitle":subtitle,"sections":sections,"fresh_defense_results":None,"human_confirmed_results":None})
    content=[
      {"title":"Calendar privacy repair prototype","bullets":["A bounded garak -> configured patch -> verify research exercise.","Reliable scheduling and observed vulnerability evidence are available.","Two defenses and the controller are implemented; 141 offline tests pass.","Fresh live defense comparison is awaiting API connectivity; human review is pending."],"notes":"Preparation-stage deck. Do not present any missing defense metric as zero or completed. Code and AI assistance are disclosed."},
      {"title":"Question and scope","bullets":["Can private event-detail publication be reduced while preserving team scheduling?","Three owner-scoped assistants; only availability is allowed to be shared.","Two Ministral model IDs, independently run as homogeneous teams.","Participant-message injection is implemented; MCP and adaptive attacks are extensions."],"notes":"This is a simplified CalBench-inspired setting, with our own generated data/code and acknowledged AI implementation assistance."},
      {"title":"Fixed synthetic calendar data","image":"calendar_example","bullets":[],"notes":"60 fixtures, 180 calendars, 2,334 fictional events. Twenty development, forty live-untested held-out. The security study uses four development cases. All plotted times UTC; the highlighted shared window is an illustration from the evaluator, not model input."},
      {"title":"Diagnosis before attacks","bullets":["v1/v2 each had 0/8 team success despite working API responses.","Missing availability, unsupported peer claims and conflicting final times were diagnosed.","v3 achieved 7/8; strict v4 schemas and an explicit shared commit achieved 40/40.","Tools compute availability/intersections; models publish, select and acknowledge."],"notes":"These are actual preserved runs, not unaided LLM reasoning claims. A valid schema or successful schedule does not establish privacy."},
      {"title":"Threat model and garak adapter","bullets":["An external peer's publish note carries the attack; attachments and system prompt remain unchanged.","Three static injection families plus benign and direct-request controls.","Actual garak Probe, Generator, Detector and ThresholdEvaluator APIs wrap the whole team.","One normal team generation uses seven model calls. Private requests are excluded from observable output."],"notes":"Custom probes reuse our authored catalog. We have not run the entire built-in garak catalog. Exact-value matches are candidate flags, not a complete semantic classifier."},
      {"title":"Observed baseline candidate flags","image":"baseline_privacy","bullets":[],"notes":"The original 40-case privacy pilot had correct scheduling in all cases. The same cases replayed through garak produced four exact-value candidates among 24 injection attempts. Initial AI review found three consistently attributed event disclosures and one real-value/misattribution case. Human confirmation pending. Replay adds no new model observations."},
      {"title":"Existing model / condition breakdown","image":"baseline_matrix","bullets":[],"notes":"Each cell is flagged/evaluable sessions, n=4 per model/condition. Small development sample does not justify a general model-safety ranking. A separate ten-session live garak smoke had 10/10 schedules correct and one candidate among six injections; it was not a defense experiment."},
      {"title":"Implemented automatic repair path","image":"repair_architecture","bullets":[],"notes":"Archived native garak discovery triggers predefined both-policy activation. Input minimizes peer prose; output releases fixed phase text. The attacker's note is inserted after its sender's own output policy. Invalid actions are rejected before any safe-text transform. Real verification is still pending connectivity."},
      {"title":"Final study is frozen and ready","bullets":["Four scenarios x two models x five conditions x four policies = 160 fresh team sessions.","Normally 1,120 logical completions; bounded retries and global resource caps.","Rotate policy order across pair blocks; match starting data and audit actual later histories.","Measure public candidate flags, scheduling correctness and raw-generation diagnostics separately.","No missing metric is treated as zero; final human rates remain undefined until review."],"notes":"The current obstacle is CONNECT 403 from the environment proxy before Mistral authentication. Keys are present but cannot yet be validated against the provider. tools/finalize_study.py --dry-run performs local readiness checks without API calls."},
      {"title":"Limits and next discussion","bullets":["Broad prose minimization is a conservative policy for this structured task, not a general semantic defense.","All human worksheets start blank; later annotation does not require another model run.","Next research: selective release, tool/MCP poisoning, adaptive attacks and held-out repeated evaluation.","Repository preserves failures, traces, source data, plans, tests and reproducibility instructions.","Applicant framing and independent reading; ChatGPT implementation and preparation assistance disclosed."],"notes":"References: garak arXiv:2406.11036 and CalBench arXiv:2605.09823. This deck is complete as a preparation artifact, but the fresh before/after research conclusion remains unexecuted and pending."}
    ]
    b.slides(None,None,ROOT/"slides",figures,basename="preparation",content_override=content)
    evidence_files=[ROOT/"experiments/garak/replay_v1/summary.json",ROOT/"experiments/garak/live_v1/summary.json",ROOT/"experiments/reliable_baseline_summary.json"]
    artifact_files=[figures/(name+"."+suffix) for name in ("baseline_privacy","baseline_matrix","calendar_example","repair_architecture") for suffix in ("png","svg","pdf")]
    artifact_files += [out/name for name in ("preparation_report.md","preparation_report.pdf","preparation_report_source.json","preparation_chart_rows.csv")]
    artifact_files += [ROOT/"slides"/name for name in ("preparation.pptx","preparation.pdf","preparation.md","preparation_source.json")]
    manifest={"built_at_utc":datetime.now(timezone.utc).isoformat(),"stage":"preparation; no fresh defense result",
              "human_review_status":"pending","fresh_live_defense_results":None,
              "sources_sha256":{str(p.relative_to(ROOT)):sha_file(p) for p in evidence_files},
              "builder_sha256":sha_file(Path(__file__)),"shared_builder_sha256":sha_file(Path(b.__file__)),
              "files_sha256":{str(p.relative_to(ROOT)):sha_file(p) for p in artifact_files}}
    save_json(out/"preparation_manifest.json",manifest)
    print("Prepared report, 10-slide PPTX/PDF, and source-backed existing-data figures. Fresh defense results remain pending.")


if __name__=="__main__":build()
