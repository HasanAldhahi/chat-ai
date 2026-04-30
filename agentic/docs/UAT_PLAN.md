# User Acceptance Testing — Phase 5 / Task 5.4

This is the operator-facing runbook for the agentic layer's UAT
campaign. UAT is fundamentally an *off-repo* activity (deploy, recruit
real users, gather feedback), so this document plans the campaign
rather than automating it. The per-cohort findings go into
`.specify/tasks/001-agentic-layer/UAT_REPORT.md`.

UAT is the gate between "automated tests pass" (Tasks 5.1–5.3) and
"production readiness" (Task 5.5). It is *not* a test of code — it is
a test of the product hypothesis: do real GWDG users find the agent
features useful and trustworthy?

---

## 1. Acceptance criteria (from Task 5.4)

| #  | Criterion                                            | Target            |
| -- | ---------------------------------------------------- | ----------------- |
| 1  | Beta environment deployed and stable                 | uptime ≥ 99 % over the cohort window |
| 2  | Cohort recruited and onboarded                       | 10–20 users       |
| 3  | Activation: users who try at least one agent session | ≥ 80 %            |
| 4  | Engagement: avg sessions per active user per week    | ≥ 5               |
| 5  | Reliability: % sessions that complete without 5xx    | ≥ 95 %            |
| 6  | Net Promoter Score (NPS) at end of cohort            | > 7               |
| 7  | Top 5 issues identified, prioritised, action-planned | per `UAT_REPORT.md` § 4 |

A campaign **passes** only when *every* row meets target. A miss on
rows 3–6 means feature, content, or stability work — not "lower the
bar."

---

## 2. Cohort and timeline

A campaign is a fixed two-week window so that engagement (row 4) is
measurable.

| Phase           | Duration | Owner                        | Output                                      |
| --------------- | -------- | ---------------------------- | ------------------------------------------- |
| Recruitment     | 1 week   | Product manager              | Signed beta agreement; participant roster   |
| Onboarding      | 1 day    | PM + engineer on-call        | Live walk-through; users have working login |
| Active usage    | 14 days  | Users (engineering on standby) | Log + survey data captured                |
| Synthesis       | 3 days   | PM + engineering lead        | `UAT_REPORT.md` § 3–6 filled in             |
| Action planning | 2 days   | Engineering lead             | GitHub issues opened, prioritised           |

**Recruitment targets** (mix matters more than count — the same 10
researchers will not surface admin-side issues):

- 4–6 researchers / postdocs (primary persona)
- 3–4 students (high-volume, low-context users)
- 2–3 admins / cluster operators
- 1–2 external collaborators (test the auth path that isn't
  GWDG-internal)

Document each participant's role in the report so feedback can be
weighted by persona.

---

## 3. Deployment (beta environment)

Beta runs on the GWDG cluster but is **isolated** from any production
chat path:

- Separate FastAPI broker process, separate vLLM model endpoint.
- Separate Vault namespace (`secret/agentic-beta/users/`) so a
  participant accidentally pushing a real PAT does not contaminate
  prod scope.
- Same Apptainer image set as prod (otherwise UAT exercises a
  different artefact than the launch).
- Banner in the chat UI: "Beta — feedback wanted at <link>." Banner is
  feature-flag controlled (`AGENTIC_BETA_BANNER=1`); ship a follow-up
  PR to add the flag if it does not exist yet.

Operator preflight before opening to users:

```bash
# On the broker host, in the beta venv:
pytest agentic/tests/security -m security
pytest agentic/tests/e2e      -m e2e
pytest agentic/tests/perf     -m perf
```

All three must be green on the deployed commit. If a fix lands during
the cohort window, re-run the affected suite and note the redeploy in
`UAT_REPORT.md` § 7 (engagement metadata).

---

## 4. Onboarding session

Single 60-minute live session per cohort. Record it (with consent) so
late joiners and retrospective analysis have ground truth. Format:

1. **0–10 min — context.** What is the agentic layer. What "agent" /
   "session" / "workspace" mean. Privacy boundaries (per-user Vault
   namespace, workspace isolation, session TTL).
2. **10–30 min — guided demo.** Engineer drives:
   - Pick an agent from the model selector.
   - Send a chat message that triggers `web_search` and `fs_write`.
   - Watch SSE actions stream in.
   - Check the workspace contents via `fs_list`.
3. **30–45 min — solo exercise.** Each participant runs a scripted
   task on their own login. Engineer monitors broker logs in real
   time.
4. **45–60 min — Q&A and survey link.** Hand out the survey link
   (`UAT_SURVEYS.md` § 1).

Onboarding outputs:
- Recording URL → `UAT_REPORT.md` § 2 (Cohort metadata).
- Live-session issues → file each as a GitHub issue tagged
  `beta-onboarding`.

---

## 5. Surveys and interviews

Three feedback channels run in parallel during the cohort window:

### 5.1 In-app micro-survey (after every 5 sessions per user)

Triggered client-side. **Not yet wired** in the broker; documented as
operator follow-up in § 9. Until it ships, the same questions go in the
post-cohort email survey.

Questions (5-point Likert except where marked):
1. The agent did what I asked.
2. I trusted the agent's outputs.
3. The streaming progress updates were useful.
4. Performance felt acceptable.
5. (Open) What surprised you, good or bad?

### 5.2 Mid-cohort email questionnaire (day 7)

10 minutes max. Covers:
- Frequency: "How many sessions did you start this week?"
- Friction: "Where did you give up or get stuck?"
- Coverage: "What did you wish the agent could do that it couldn't?"
- Trust: "Were there outputs you double-checked or distrusted?"
- Bug roll-up: "Anything broken?" (free text)

### 5.3 Post-cohort interviews (day 14–17)

30-minute one-on-one with **5–7** participants chosen for spread
across personas. Drive against the field guide in
`UAT_REPORT.md` § 5 ("Interview prompts") so synthesis can compare.

NPS is asked *only* in the post-cohort survey (one canonical
score per cohort). Computed as
`(promoters % - detractors %)` on the standard 0–10 scale.

---

## 6. Metric capture

UAT metrics come from three sources:

| Metric                         | Source                                                                       | Captured by                                  |
| ------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------- |
| Activation (≥1 session)        | broker audit log: count(distinct user) where event=`agent_chat_started`      | log query (§ 6.1)                            |
| Sessions / user / week         | broker audit log: group by user, week, count `agent_chat_started`            | log query (§ 6.1)                            |
| Successful-session rate        | audit log: 1 - (count `agent_chat_failed_5xx` / count `agent_chat_started`)  | log query (§ 6.1)                            |
| NPS                            | post-cohort survey (one row per user)                                        | survey export                                |
| In-app sentiment trend         | per-5-sessions micro-survey                                                  | survey export (or email if § 5.1 not wired)  |
| Stability (uptime)             | platform monitoring (Grafana, follow-up from Task 5.3 § 5)                   | dashboard screenshot                         |

### 6.1 Log-derived metric queries

The broker writes structured JSON-line audit events. Until a real BI
pipeline lands, run these from the broker's working directory:

```bash
# Activation: distinct users who started ≥1 agent session.
jq -r 'select(.event=="agent_chat_started") | .user' broker.jsonl \
  | sort -u | wc -l

# Sessions per user (full cohort window).
jq -r 'select(.event=="agent_chat_started") | .user' broker.jsonl \
  | sort | uniq -c | sort -rn

# Failure rate.
total=$(jq 'select(.event=="agent_chat_started")' broker.jsonl | wc -l)
fail=$(jq  'select(.event=="agent_chat_failed_5xx")' broker.jsonl | wc -l)
python3 -c "print(f'success rate: {1 - $fail/$total:.3f}')"
```

If `audit_logger.py` does not yet emit `agent_chat_started` /
`agent_chat_failed_5xx`, file that as a blocker before the cohort
opens — this is a Task 5.4 prerequisite, not a follow-up.

Confirm before announcing the cohort:

```bash
grep -E "agent_chat_started|agent_chat_failed_5xx" agentic/app/services/audit_logger.py
```

If the grep is empty, the cohort cannot start — the metrics are not
measurable.

---

## 7. Issue triage during the cohort

Bugs surfaced during the active-usage window go straight into GitHub
with a `beta` label. Triage daily standup:

| Severity   | Definition                                      | Response                                  |
| ---------- | ----------------------------------------------- | ----------------------------------------- |
| Sev-1      | Auth bypass, data leak between users, full outage | Stop cohort; fix; redeploy; resume.       |
| Sev-2      | Common workflow broken for ≥1 persona           | Same-day fix if possible; banner if not.  |
| Sev-3      | Single-user friction, polish, content           | Triaged into post-UAT backlog.            |

Sev-1 *halts the cohort*. Sev-2/3 do not — keep the engagement window
running so engagement metrics stay clean.

---

## 8. Sign-off

The UAT campaign is complete when:

- `UAT_REPORT.md` is filled in for the cohort.
- All 7 acceptance rows in § 1 above have a measured value, and at
  least 6 of 7 are at-or-above target. (Row 7 — top-5 issues — is
  always met by definition; the rows that matter are 1–6.)
- Action plan opened: every Sev-1/Sev-2 issue has a GitHub issue with
  an owner and a target version.
- PM + engineering lead countersign in `UAT_REPORT.md` § 8.
- `PRODUCTION_CHECKLIST.md` § 5.4 ticked.

If 2+ rows from § 1 missed target, re-plan and run a second cohort
*after* shipping the action-plan fixes. Do not close 5.4 by waiving
the bar — Task 5.5 (production readiness) depends on a real pass.

---

## 9. Operator follow-ups (deferred from this task)

These are scoped out of in-repo work because they require a deployed
beta environment to validate:

* **In-app micro-survey delivery.** Add a `/api/agent/feedback` POST
  endpoint and a chat-UI prompt that fires after every 5
  `agent_chat_started` events for a user. Until this ships, channel
  5.1 falls back to email (see § 5.2).
* **`AGENTIC_BETA_BANNER` feature flag** in the chat UI.
* **Audit-log emission for `agent_chat_started` /
  `agent_chat_failed_5xx`** if not already present (verify in § 6.1).
* **Survey tooling.** Pick one (Google Forms / Typeform / internal
  GWDG tool) and link the URL into `UAT_REPORT.md` § 2 before
  recruitment opens.
