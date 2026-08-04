# Identity-Scoped Execution Control for AI Agents in Cloud Infrastructure
### Final Research Plan — Methodology, SOP, and SRS

**Author:** Binod Prasad Joshi
**Status:** Final pre-research planning document
**Version:** 2.0

---

## 1. Problem Statement

AI agents are increasingly given direct write-access to cloud infrastructure — running `terraform apply`, calling AWS APIs, modifying IAM policies, triggering GitHub Actions. Current industry data (2026) shows the majority of organizations grant agents broader privileges than they'd give a human doing the same task, and there is no standard way to attribute a specific infrastructure action to the specific agent, session, or reasoning chain that triggered it. No enforcement layer currently scopes what an agent is *allowed* to do based on its stated task at the moment of execution — permissions are static (IAM roles), not dynamic and task-aware.

**Research question:** Can a lightweight proxy layer dynamically scope an AI agent's infrastructure permissions to its stated task, and attribute every resulting infrastructure action to that agent/session, without materially degrading legitimate agent performance?

---

## 2. Objectives

1. Design and implement a proxy/interceptor layer that sits between an AI agent's tool-calling interface and real infrastructure APIs (Terraform CLI, AWS SDK, GitHub Actions).
2. Attach identity metadata (agent ID, session ID, task description, timestamp, reasoning excerpt) to every intercepted call before execution.
3. Implement dynamic least-privilege scoping — compute the minimal permission set required for a stated task and reject/flag calls outside that scope.
4. Produce a queryable audit trail suitable for incident response.
5. Empirically evaluate: block rate on off-scope/malicious actions, false-positive rate on legitimate actions, attribution accuracy, and performance overhead.
6. Position the result against existing policy-enforcement systems, not just a no-proxy baseline.
7. Publish results as a reproducible open-source tool plus a paper.

---

## 3. Threat Model

**Assets:** cloud resources (compute, storage, IAM policies, networking) reachable by an AI agent's tool-use interface.

**Trust boundary:** the boundary sits between the agent's declared task/reasoning (untrusted — may be manipulated by prompt injection, misinterpretation, or a compromised upstream instruction) and the infrastructure APIs (trusted execution surface once a call is authorized).

**Attacker assumptions:**
- The agent's input (user prompt, retrieved content, tool outputs feeding back into context) may contain adversarial or injected instructions the agent did not originate.
- The agent itself is not assumed malicious by design, but its *effective* behavior at execution time cannot be fully predicted from its stated task alone.
- The attacker does not have direct access to cloud credentials — the threat is the agent being induced to misuse the credentials/scope it already has.

**Out of scope:** compromise of the underlying LLM weights, supply-chain attacks on the proxy itself, and attacks that don't route through the tool-calling interface (e.g. direct console access) are not covered by this system and are noted as limitations.

**What the system defends against:** an agent whose declared task is narrow but whose actual tool calls attempt broader or unrelated actions (scope creep, prompt-injected privilege escalation, accidental overreach).

**What it does not defend against:** an agent that stays within a maliciously broad *declared* task scope, or attacks bypassing the proxy entirely.

---

## 4. Related Work and Positioning

| Prior work | What it does | Gap this research fills |
|---|---|---|
| RIVA (2026) | Multi-agent LLM verification for configuration drift detection, robust to unreliable tool outputs | Detects drift after the fact; does not scope or attribute *who* is allowed to act before execution |
| Agentic IaC closed-loop framework (2026) | Continuous drift detection/correction using AI agents embedded in the IaC lifecycle | Focused on detection/correction loop, not identity or permission scoping |
| MARLISE | Multi-agent RL for resource scaling decisions | Different problem (scaling), not access control |
| NIST AI Agent Standards Initiative (Feb 2026) | Announced research direction on agent authentication/identity, standards still in development | No working technical implementation yet — this research produces one |
| Industry survey data (Gravitee, Teleport, 2026) | Documents the governance/execution gap quantitatively | Confirms the gap exists; does not propose or test a solution |
| Open Policy Agent (OPA) | General-purpose policy engine, static declarative policies evaluated per request | Not task-aware or agent-identity-aware out of the box; ScopeGuard could plausibly sit on top of OPA as a policy backend — worth discussing as an implementation option, not a competitor to dismiss |
| AWS Cedar | Policy language for fine-grained authorization, used in AWS Verified Permissions | Same category as OPA — static policy evaluation, not dynamic task-to-scope inference from natural language |
| Kubernetes RBAC / AWS IAM | Static role-based access control, assigned ahead of time | The baseline this research compares against directly — the "static permissions" half of the research question |
| SPIFFE/SPIRE | Workload identity framework | Solves *identity* for workloads, not task-aware scoping — complementary, worth citing in lit review as identity infrastructure this could integrate with |

**Novelty claim (revised, hedged appropriately):** To the best of our knowledge, this is among the first open-source implementations of task-aware permission scoping combined with identity attribution specifically for AI-agent-driven infrastructure operations, evaluated empirically against injected malicious/off-scope behavior. This is not claimed as the first work touching AI agents and cloud governance broadly — that space is active — but as a working system where prior work has so far been either detection-after-the-fact (RIVA) or a stated research direction without a public implementation (NIST initiative).

---

## 5. Research Methodology

### 5.1 Type of research
Applied/experimental systems research — design, build, and empirically evaluate a working artifact against both a no-proxy baseline and, where feasible, existing policy-engine behavior (Section 4).

### 5.2 Approach
1. **Design phase** — define the proxy architecture, permission-scoping algorithm, threat model (Section 3), and metadata schema.
2. **Build phase** — implement the proxy in Python (FastAPI), integrating with an LLM tool-use loop (Claude, tool-use) and a sandboxed AWS environment (LocalStack) plus Terraform.
3. **Experiment design** — construct a task set: legitimate infra tasks and adversarial/off-scope/prompt-injected tasks (Section 8, Phase 2).
4. **Data collection** — run all sessions through the proxy, log every intercepted call, scoping decision, and outcome.
5. **Evaluation** — compute metrics (Section 7), compare against a no-proxy baseline (static IAM only), and run the ablation study (Section 5.4).
6. **Write-up** — IMRaD format: methodology, results, limitations, related work, reproducibility package.

### 5.3 Variables
- **Independent variable:** presence/absence of the scoping proxy; identity tagging alone vs. identity tagging + active scoping; task type (legitimate vs. adversarial/off-scope).
- **Dependent variables:** block rate, false-positive rate, attribution accuracy, precision/recall/F1, latency overhead per call.

### 5.4 Ablation Study
To isolate which component contributes what, run three configurations against the same 200-task set:
1. **No proxy** (raw baseline).
2. **Identity tagging only** — logs and attributes every call, but never blocks (measures attribution accuracy and logging overhead in isolation).
3. **Identity tagging + active scoping** — full system (measures the added value of enforcement on top of attribution).

This isolates whether performance overhead and false positives come from the logging layer or the scoping/enforcement layer specifically — a detail reviewers will ask about if it's absent.

---

## 6. Software Requirements Specification (SRS)

### 6.1 Purpose
Define the functional and non-functional requirements for the proxy system ("ScopeGuard" — working name) used to conduct the research.

### 6.2 Scope
ScopeGuard intercepts tool calls made by an AI agent toward Terraform CLI, AWS SDK (boto3), and GitHub Actions API, scopes them against the agent's declared task, logs them with identity metadata, and allows/blocks execution.

### 6.3 Functional Requirements
- **FR1:** System shall intercept all outbound Terraform/AWS SDK/GitHub Actions calls made through the agent's tool-use interface.
- **FR2:** System shall extract and attach agent ID, session ID, declared task, and a reasoning snippet to each intercepted call.
- **FR3:** System shall compute a minimal required permission set from the declared task using a rule/keyword-based classifier. This is the baseline mechanism for this project; semantic/embedding-based or OPA-backed scope inference is noted as future work (Section 10), not claimed as implemented.
- **FR4:** System shall compare each call's actual required permission against the computed scope; calls outside scope shall be blocked or flagged per configurable policy (block / warn / log-only).
- **FR5:** System shall persist an audit log (call, decision, timestamp, identity metadata) to a queryable store (SQLite/PostgreSQL).
- **FR6:** System shall expose a query API (FastAPI) to retrieve audit history by agent, session, or time range.
- **FR7:** System shall support an identity-tagging-only mode (log, never block) to support the ablation study in Section 5.4.

### 6.4 Non-Functional Requirements
- **NFR1 (Performance):** Added latency per intercepted call shall not exceed 200ms on average; actual measured overhead reported, not assumed.
- **NFR2 (Reliability):** System shall fail closed (block) on internal errors, not fail open.
- **NFR3 (Portability):** Must run against LocalStack for testing and real AWS for optional live validation, without code changes beyond endpoint config.
- **NFR4 (Reproducibility):** All experiment configs, task sets, and logs shall be scriptable and version-controlled for reproducibility.
- **NFR5 (Security):** No credentials or secrets shall be logged in the audit trail.

### 6.5 System Architecture (high level)
```
AI Agent (Claude, tool-use loop)
        |
        v
 ScopeGuard Proxy (FastAPI)
   - Identity tagger
   - Task-to-scope classifier (rule-based)
   - Policy engine (allow/block/warn)
   - Audit logger
        |
        v
 Sandboxed/real backend: Terraform CLI | boto3 (LocalStack/AWS) | GitHub Actions API
```

### 6.6 Sequence Diagram (request flow, described)
1. User gives the agent a task.
2. Agent reasons and decides to invoke a tool (e.g. `boto3.create_bucket`).
3. Call is intercepted by ScopeGuard before reaching AWS/Terraform/GitHub.
4. ScopeGuard tags the call with identity metadata (agent ID, session ID, declared task).
5. Task-to-scope classifier computes the allowed action set for the declared task.
6. Policy engine compares the actual call against the allowed set.
7. Decision: ALLOW → call forwarded to LocalStack/AWS/Terraform/GitHub; BLOCK/WARN → call rejected or flagged, structured error returned to the agent loop.
8. Audit logger persists the full record regardless of decision.
(Render this as an actual sequence diagram — e.g. Mermaid or a drawn figure — when writing the paper; described here as the reference for that diagram.)

### 6.7 Tech Stack
- Language: Python 3.11+
- API layer: FastAPI
- Agent/LLM: Claude (via API, tool-use)
- Infra sandbox: LocalStack (free, local AWS emulation) + Terraform
- Storage: SQLite for dev, PostgreSQL for scaled experiments
- Testing: pytest, asyncio
- Version control: GitHub (public repo for reproducibility)

### 6.8 Constraints
- Home setup: no paid cloud budget required for core experiments (LocalStack covers AWS simulation); optional small real-AWS validation run within free-tier limits.
- Solo researcher: architecture must stay small enough to build and test individually within available time before submission deadline.

---

## 7. Evaluation Metrics

| Metric | Definition | Target |
|---|---|---|
| Block rate (adversarial) | % of off-scope/malicious actions correctly blocked | High (report actual %) |
| False positive rate | % of legitimate actions incorrectly blocked | Low (report actual %) |
| Precision / Recall / F1 | Standard classification metrics on the scoping decision | Report actual values from the confusion matrix |
| Attribution accuracy | % of logged actions correctly tied to originating agent/session/task | Near 100% (deterministic by design — validate no gaps) |
| Latency overhead | Added ms per call vs. no-proxy baseline | < 200ms average, measured not assumed |
| Overhead breakdown (ablation) | Latency/accuracy split between identity-tagging-only vs. full scoping (Section 5.4) | Report both configurations separately |

---

## 8. Standard Operating Procedure (SOP) — Execution Plan

### Phase 1 — Environment Baseline & Core Setup 
1. Initialize a public GitHub repo with structured directories: `/proxy`, `/agent`, `/tests`, `/data`, plus README and license (MIT/Apache).
2. Spin up LocalStack locally via Docker Compose:
   ```yaml
   services:
     localstack:
       image: localstack/localstack
       ports:
         - "4566:4566"
   ```
3. Install Terraform CLI, set it to target the LocalStack endpoint.
4. Build the base FastAPI interceptor: a `/execute-tool` endpoint that receives outbound boto3/Terraform call payloads, checks them against a SQLite scope table, and tags each with a UUID4 tracking ID.
5. Define the audit-log metadata schema and implement logging to SQLite. Example entry:
   ```python
   audit_entry = {
       "session_id": str(uuid.uuid4()),
       "agent_id": "claude-sonnet",
       "declared_task": task_prompt,
       "intercepted_call": api_call_name,
       "scoping_decision": "BLOCKED" if is_adversarial else "ALLOWED",
       "latency_ms": performance_counter_delta * 1000,
   }
   ```

### Phase 2 — Scoping Engine, Threat Set & Threat Model Validation 
6. Define a taxonomy of infra actions and risk levels (create/read/update/delete, per resource type).
7. Build the rule-based task-to-scope classifier: task description → allowed action list. Described honestly as keyword/rule-based (Section 6.3, FR3) — no overclaiming.
8. Implement the policy engine (allow/block/warn) with a configurable threshold; fail-closed by default (NFR2), with the tradeoff discussed in the write-up rather than an untested timeout value picked in advance.
9. Build the evaluation task set: 100 clean tasks (explicit, safe operations — e.g. "deploy an EC2 instance in a private subnet") and 100 adversarial tasks (prompt-injected or malicious — e.g. "update the webserver, and also delete the CloudWatch log retention policy"), constructed to match the threat model in Section 3.
10. Implement the ablation configurations from Section 5.4 (no proxy / tagging-only / full scoping).

### Phase 3 — Automated Testing 
11. Write an async pytest/asyncio driver that runs all 200 tasks through all three ablation configurations.
12. Log every call using the audit schema above; capture latency per call across all configurations.

### Phase 4 — Analysis & Write-up 
13. Pull results from SQLite and compute the confusion matrix (TP/TN/FP/FN) for scoping decisions; derive accuracy, precision, recall, F1, and the metrics in Section 7.
14. Generate charts: block rate across adversarial task categories (bar chart), latency per call vs. the 200ms NFR1 target across configurations (line chart), and ablation comparison (tagging-only vs. full scoping).
15. Manually review every false positive/negative to characterize failure modes.
16. Draft the paper in IMRaD format: Introduction, Related Work (Section 4 table), Threat Model (Section 3), Methods (Section 5/6), Results, Discussion, Limitations, Conclusion.
17. Render the sequence diagram (Section 6.6) and architecture diagram (Section 6.5) as actual figures.
18. Prepare the reproducibility package: code, task set, config, README with run instructions. Every number in the paper must trace back to a logged result — no invented figures.

### Phase 5 — Submission 
19. Post to arXiv (cs.CR / cs.SE / cs.DC as appropriate).
20. Target venue: IEEE Cloud Computing conference/workshop, CSA Research, or an AI-agent-safety workshop — check current calls-for-papers close to submission time since these shift. USENIX Security/SOSP/OSDI-tier venues are not realistic targets for this scope — don't aim there.
21. Submit, iterate on reviewer feedback if applicable.

---

## 9. Risk Register

| Risk | Mitigation |
|---|---|
| Rule-based classifier called simplistic by a reviewer | Describe it accurately as a rule/keyword-based baseline (FR3); discuss semantic/OPA-backed alternatives as future work only |
| LocalStack doesn't fully replicate real AWS behavior for some services | Scope experiments to well-supported LocalStack services (S3, EC2, IAM, RDS-basic); note as a limitation |
| Small task-set size limits statistical power | Be transparent about sample size in the paper; treat as a systems/case-study contribution, not a large-scale statistical claim |
| Novelty challenged by concurrent work | Use hedged claim language (Section 4) from the start rather than "first ever" |
| Timeline slips against thesis/work commitments | Weekly buffer built into phase estimates; Phase 2/3 are most compressible if needed |

---

## 10. Future Work (explicitly not part of this project's scope)

- Semantic/embedding-based or LLM-assisted scope inference in place of the rule-based classifier.
- Integration with an existing policy engine (OPA or Cedar) as the enforcement backend instead of a custom policy engine.
- Multi-agent concurrent-session scalability testing.
- Real-AWS large-scale validation beyond the free-tier sanity check.

---

## 11. Deliverables Checklist

- [ ] Public GitHub repo with working ScopeGuard proxy
- [ ] Labeled task set (100 legitimate + 100 adversarial) checked into repo
- [ ] Ablation experiment logs and analysis scripts
- [ ] Architecture and sequence diagrams
- [ ] Draft paper (arXiv-ready, IMRaD format)
- [ ] Reproducibility README
