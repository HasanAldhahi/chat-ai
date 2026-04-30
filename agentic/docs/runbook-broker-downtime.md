# Runbook: FastAPI Broker Downtime (Task 5.5 Production Readiness)

## Overview

This runbook provides procedures for diagnosing and resolving FastAPI broker downtime in the agentic layer.

## Symptoms

- Health check `/health` returns 5xx or times out
- All HTTP requests to broker fail
- Grafana alerts: "Broker down" or "High error rate"
- Users cannot reach agent endpoints

## Diagnosis

### 1. Check Service Health

```bash
# Check Kubernetes deployment status
kubectl get pods -n agentic -l app=agentic-broker

# Check pod logs
kubectl logs -f deployment/agentic-broker -n agentic --tail=100
```

### 2. Check Resource Usage

```bash
# Pod resource consumption
kubectl top pods -n agentic -l app=agentic-broker

# Check if pod is OOMKilled
kubectl describe pod <pod-name> -n agentic | grep -i oom
```

### 3. Check Network Connectivity

```bash
# Check service endpoints
kubectl get endpoints agentic-broker -n agentic

# Test connectivity from outside
curl -k https://agentic.gwdg.de/health
```

### 4. Check Prometheus Metrics

```bash
# Query Prometheus directly
curl -G 'http://prometheus.gwdg.de/api/v1/query' \
  --data-urlencode 'query=up{job="agentic-broker"}'

# Check metrics endpoint
curl http://agentic.gwdg.de/metrics | grep "^up"
```

### 5. Check Recent Deployments

```bash
# Check deployment history
kubectl rollout history deployment/agentic-broker -n agentic

# Check recent events
kubectl get events -n agentic --sort-by='.lastTimestamp' --field-selector involvedObject.kind=Pod
```

## Common Issues and Resolutions

### Issue 1: Pod CrashLoopBackOff

**Cause:** Application error on startup (config issue, dependency failure, code bug).

**Resolution:**

1. Check pod logs for error:

```bash
kubectl logs -f <pod-name> -n agentic
```

2. Check for startup dependencies:

- Vault connection config
- Slurm REST API reachable
- vLLM endpoint available

3. If config issue, update ConfigMap:

```bash
kubectl edit configmap agentic-broker-config -n agentic
```

4. Restart pod:

```bash
kubectl rollout restart deployment/agentic-broker -n agentic
```

5. If code bug, rollback to previous version:

```bash
kubectl rollout undo deployment/agentic-broker -n agentic
```

### Issue 2: OOMKilled (Out of Memory)

**Cause:** Memory limit exceeded, memory leak, or traffic spike.

**Resolution:**

1. Check memory usage history:

```bash
kubectl top pod <pod-name> -n agentic --containers
```

2. Increase memory limits if needed:

```bash
kubectl set resources deployment agentic-broker \
  -n agentic --limits=memory=2Gi --requests=memory=1Gi
```

3. If memory leak, restart pods:

```bash
kubectl rollout restart deployment/agentic-broker -n agentic
```

4. Investigate for code-level leaks (check metrics for increasing heap).

### Issue 3: High CPU / Latency

**Cause:** Insufficient resources, inefficient queries, or traffic surge.

**Resolution:**

1. Scale horizontally:

```bash
kubectl scale deployment agentic-broker --replicas=4 -n agentic
```

2. Check for inefficient queries (slow DB calls, Slurm API loops):

```bash
kubectl logs deployment/agentic-broker -n agentic | grep "duration_ms" | tail -20
```

3. Enable HPA (Horizontal Pod Autoscaler):

```bash
kubectl autoscale deployment agentic-broker \
  --cpu-percent=70 --min=2 --max=10 -n agentic
```

### Issue 4: Database Connection Failed

**Cause:** Database unreachable, credentials rotated, connection pool exhausted.

**Resolution:**

1. Check database health:

```bash
# For Postgres (if used)
kubectl get pods -n postgres -l app=postgres

# Test connection
kubectl run -it --rm debug --image=postgres:15 --restart=Never -- \
  psql -h postgres.gwdg.de -U agentic -d agentic_db
```

2. Rotate credentials in Vault:

```bash
vault kv put -mount=kv agentic/db \
  username=agentic password=$(openssl rand -base64 32)
```

3. Restart broker to pick up new credentials.

### Issue 5: Configuration Drift

**Cause:** ConfigMap change not propagated or wrong env var.

**Resolution:**

1. Compare running config vs ConfigMap:

```bash
kubectl describe deployment/agentic-broker -n agentic | grep -A 20 Environment
kubectl get configmap agentic-broker-config -n agentic -o yaml
```

2. Update ConfigMap:

```bash
kubectl edit configmap agentic-broker-config -n agentic
```

3. Restart for changes to take effect:

```bash
kubectl rollout restart deployment/agentic-broker -n agentic
```

## Emergency Recovery

### Immediate Rollback

If recent deployment caused outage:

```bash
# Undo last deployment
kubectl rollout undo deployment/agentic-broker -n agentic

# Verify health
kubectl get pods -n agentic
curl -k https://agentic.gwdg.de/health
```

### Temporary Disable Auth

If auth issue blocking users:

```bash
# Set env var to disable auth (use with caution!)
kubectl set env deployment/agentic-broker AGENTIC_AUTH_MIDDLEWARE_ENABLED=false -n agentic

# Restart
kubectl rollout restart deployment/agentic-broker -n agentic
```

⚠️ Re-enable auth immediately after issue resolved.

### Node Drain

If node failing:

```bash
# Identify stuck pod node
kubectl get pods -n agentic -o wide

# Cordon and drain node
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# New pods will schedule on other nodes
```

## Escalation

If unresolved after 30 minutes:

1. Contact on-call engineering team
2. Keep detailed logs:
   - `kubectl logs deployment/agentic-broker -n agentic > outage-logs.txt`
   - `kubectl describe pod <pod> -n agentic > pod-describe.txt`
   - `kubectl top pods -n agentic > resource-usage.txt`
3. Open incident in incident management system

## Prevention

- Run regular liveness/readiness probes
- Set up HPA for automatic scaling
- Monitor memory/CPU trends in Grafana
- Test deployments in staging first
- Run chaos experiments (e.g., kill pods) to test recovery
- Set up alerts for:
  - Pod > 1 restart in 5 minutes
  - P99 latency > 2 seconds
  - Error rate > 1%
  - CPU/Memory > 80% threshold

## Metrics

Key metrics to monitor:

- `up{job="agentic-broker"}` - Broker up/down
- `http_requests_total{status_code=~"5.."}` - 5xx error rate
- `http_request_duration_seconds{quantile="0.99"}` - P99 latency
- `active_sessions` - Active user sessions
- `process_resident_memory_bytes` - Memory usage
- `process_cpu_seconds_total` - CPU usage

## Related Documentation

- [FastAPI deployment guide](https://fastapi.tiangolo.com/deployment/)
- [Kubernetes troubleshooting](https://kubernetes.io/docs/tasks/debug/)
- [Prometheus operational guide](https://prometheus.io/docs/operating/)