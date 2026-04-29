# Production rollout checklist (Phase 5 summary)

Derived from `tasks.md` Tasks 5.1–5.5. This file is a **planning aid**; execution
is environment-specific.

## 5.1 Security / pentest
- [ ] Third-party penetration test on broker + MCP boundary
- [ ] Review Slurm job env injection and Vault paths

## 5.2 End-to-end
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
