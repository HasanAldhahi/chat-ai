# User Acceptance Test Report — Agentic Layer

**Branch:** `task-5.4-uat` (off `task-5.3-performance-testing`)
**Spec source:** `.specify/tasks/001-agentic-layer/tasks.md` § Task 5.4
**Runbook:** `agentic/docs/UAT_PLAN.md`
**Status:** template — fill in per cohort

One report per cohort. If a second cohort is needed (see runbook § 8),
copy this file to `UAT_REPORT_2.md` and fill in the new run; keep the
first one as historical record.

---

## 1. Acceptance scoreboard

Fill in once at end of cohort. Pull numbers from runbook § 6.

| #  | Criterion                                            | Target | Measured | Pass? |
| -- | ---------------------------------------------------- | ------ | -------- | ----- |
| 1  | Beta uptime over the cohort window                   | ≥ 99 % |          | ☐     |
| 2  | Cohort size                                          | 10–20  |          | ☐     |
| 3  | Activation: users who tried ≥1 agent session         | ≥ 80 % |          | ☐     |
| 4  | Engagement: avg sessions per active user per week    | ≥ 5    |          | ☐     |
| 5  | Reliability: % sessions that completed without 5xx   | ≥ 95 % |          | ☐     |
| 6  | Net Promoter Score                                   | > 7    |          | ☐     |
| 7  | Top 5 issues identified, prioritised, action-planned | yes    |          | ☐     |

Overall verdict (circle): **pass** / **partial — re-cohort needed** / **fail**.

---

## 2. Cohort metadata

- **Cohort window:** _YYYY-MM-DD_ → _YYYY-MM-DD_
- **Commit SHA on beta deploy:** `__________________`
- **Beta broker URL:** ____________________
- **Beta vLLM endpoint:** ____________________
- **Survey tool URL:** ____________________
- **Onboarding recording URL:** ____________________
- **PM owner:** ____________________
- **Engineering lead:** ____________________
- **Re-deploys during cohort** (commit + reason):
  - ____________________
  - ____________________

### 2.1 Participants

| ID    | Persona      | Onboarded? | Sessions started | Sessions ok | Survey returned? | NPS | Notes                  |
| ----- | ------------ | ---------- | ---------------- | ----------- | ---------------- | --- | ---------------------- |
| P-01  | researcher   | ☐          |                  |             | ☐                |     |                        |
| P-02  | researcher   | ☐          |                  |             | ☐                |     |                        |
| P-03  | student      | ☐          |                  |             | ☐                |     |                        |
| P-04  | student      | ☐          |                  |             | ☐                |     |                        |
| P-05  | admin        | ☐          |                  |             | ☐                |     |                        |
| P-06  | external     | ☐          |                  |             | ☐                |     |                        |
| ...   |              |            |                  |             |                  |     |                        |

(Add rows up to the actual cohort size. Anonymise — match `P-NN` to
real identity in a separate, access-controlled doc.)

---

## 3. Quantitative findings

### 3.1 Activation funnel

| Stage                          | Count | % of cohort |
| ------------------------------ | ----- | ----------- |
| Onboarded                      |       |             |
| Logged in to beta              |       |             |
| Sent ≥1 chat message           |       |             |
| Started ≥1 agent session       |       |             |
| Started ≥5 agent sessions      |       |             |

Where the funnel falls off is the strongest signal — annotate any
step where drop is > 30 %.

### 3.2 Engagement

- **Sessions started, total:** _____
- **Sessions per active user per week:** _____ (target ≥ 5)
- **Median session duration (s):** _____
- **% sessions that triggered ≥1 tool call:** _____

### 3.3 Reliability

- **Sessions completed without 5xx:** _____ / _____ ( _____ %)
- **Top 5xx routes** (route → count):
  - ____________________
  - ____________________

### 3.4 Performance under real load (cross-check Task 5.3)

If beta exposes Grafana, capture peak values during the cohort:

- **P99 first-action latency observed:** _____ ms
- **P95 SSE publish→deliver observed:** _____ ms
- **Broker CPU peak:** _____ %
- **Worst RSS over 30-min sample:** _____ MB

Compare against the targets in `PERFORMANCE_REPORT.md` § 1. If a
target is breached only under real-user shape (and not the Locust
campaign), document the divergence in § 6 — this is the canonical
"users find what tests don't" payoff of UAT.

---

## 4. Top issues

Up to 10 rows; rank by severity then user-impact count.

| Rank | Severity | Title                              | Affected personas | Repro / artefact            | Owner | GitHub issue | Target |
| ---- | -------- | ---------------------------------- | ----------------- | --------------------------- | ----- | ------------ | ------ |
| 1    |          |                                    |                   |                             |       |              |        |
| 2    |          |                                    |                   |                             |       |              |        |
| 3    |          |                                    |                   |                             |       |              |        |
| 4    |          |                                    |                   |                             |       |              |        |
| 5    |          |                                    |                   |                             |       |              |        |

"Severity" uses the runbook § 7 scale (Sev-1 / Sev-2 / Sev-3).
"Target" is the version / sprint where the fix lands.

---

## 5. Interview prompts (qualitative)

Drive each one-on-one against the same questions so themes can be
compared across participants.

1. Walk me through the most useful thing the agent did for you.
2. Walk me through the most frustrating thing.
3. Was there a moment you didn't trust the output? What did you do?
4. Did the streaming progress (the action / result events) help or
   distract?
5. If you had to pitch this feature to a colleague in one sentence,
   what would you say?
6. What would make you stop using it after one week?

Capture verbatim quotes where they crystallise a theme; testimonials
land in § 7.

### 5.1 Theme synthesis

Cluster recurring observations. For each theme, list participant IDs
and a short summary.

| Theme                         | Participants    | Summary                                             |
| ----------------------------- | --------------- | --------------------------------------------------- |
| _ex._ "agent felt slow on first action" | P-01, P-04, P-09 | First-action latency on cold start was unacceptable. |
|                               |                 |                                                     |
|                               |                 |                                                     |

---

## 6. UAT-only divergences

Behaviour that UAT caught and the automated suites didn't. This list
is the *output* of the campaign — keep it ruthless. If the list is
empty, UAT was probably under-loaded.

Format:

```
### D-XXX  <one-line title>
- Surfaced by: <participant IDs>
- Surface: <UI / broker / MCP / Slurm / vLLM>
- Why automated suite missed it: <single sentence>
- Repro: <steps>
- Action: <new test? new monitor? feature change?>
```

---

## 7. Testimonials

Direct quotes (with consent) for launch comms. Attribute by persona,
not name, unless the participant gave explicit OK.

> _"…"_ — researcher, P-XX

> _"…"_ — student, P-XX

---

## 8. Sign-off

- [ ] § 1 scoreboard filled in; verdict recorded.
- [ ] Every Sev-1/Sev-2 row in § 4 has a GitHub issue + owner + target.
- [ ] § 6 (UAT-only divergences) reviewed in engineering retro.
- [ ] PM countersign: _________________________  date: __________
- [ ] Engineering lead countersign: _________________________  date: __________
- [ ] `PRODUCTION_CHECKLIST.md` § 5.4 ticked.

If verdict is "partial — re-cohort needed", do **not** sign off. Open
a follow-up branch and copy this template to `UAT_REPORT_2.md` after
the action-plan fixes ship.
