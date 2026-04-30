# Production rollout checklist (Phase 5 summary)

Derived from `tasks.md` Tasks 5.1–5.5. This file is a **planning aid**; execution
is environment-specific.

## 5.1 Security / pentest
- [ ] Run `pytest agentic/tests/security/ -m security` (automated regression suite — see `task-5.1-security-pentest`)
- [ ] Walk through every row in `SECURITY_PENTEST_REPORT.md` for the deployed environment
- [ ] Third-party penetration test on broker + MCP boundary
- [ ] Review Slurm job env injection and Vault paths
- [ ] Pentester sign-off recorded in `SECURITY_PENTEST_REPORT.md` § 7

## 5.2 End-to-end
- [ ] Run `pytest agentic/tests/e2e/ -m e2e` (backend integration suite — see `task-5.2-end-to-end-testing`; 48 tests, ~1.4 s)
- [ ] Wire the security + e2e suites as a CI gate that blocks PR merge — see `agentic/docs/E2E_TESTING.md` § 3
- [ ] Implement Playwright UI suite per `agentic/docs/E2E_TESTING.md` § 2 once a deployable stack is reachable
- [ ] Chat UI → Node → broker → vLLM smoke (agent model)
- [ ] Slurm job → Apptainer → MCP + agent smoke on cluster

## 5.3 Performance
- [ ] Broker SSE load sample (target 100 msg/s per session cap)
- [ ] vLLM latency SLO

## 5.4 UAT
- [ ] Pilot user cohort sign-off

## 5.5 Production readiness
- [ ] Runbooks, on-call, rollback drill
- [ ] Monitoring dashboards for broker + inference
