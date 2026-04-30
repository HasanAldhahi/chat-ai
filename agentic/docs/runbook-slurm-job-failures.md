# Runbook: Slurm Job Failures (Task 5.5 Production Readiness)

## Overview

This runbook provides procedures for diagnosing and resolving Slurm job failures in the agentic layer.

## Symptoms

- Agent session fails to start
- User receives 5xx error on job submission
- Session stuck in "queued" or "running" state indefinitely
- Job cancelled unexpectedly

## Diagnosis

### 1. Check Job Status

Use the Slurm REST API to check job status:

```bash
# Get job status
curl -H "Authorization: Bearer <token>" \
  https://slurmrestd.gwdg.de:6820/slurm/v0.0.40/job/<job_id>
```

Or use `sacct` (on Slurm controller):

```bash
sacct -j <job_id> --format=JobID,JobName,State,ExitCode,NodeList,Start,End,Elapsed
```

### 2. Check Broker Logs

```bash
# Real-time logs
kubectl logs -f deployment/agentic-broker -n agentic

# Search for job errors
kubectl logs deployment/agentic-broker -n agentic | grep "slurm" | grep -i error
```

### 3. Check Apptainer Container

Verify the Apptainer image is accessible:

```bash
# Check image exists on shared storage
ls -lh /shared/containers/agentic-base.sif

# Try manual pull (image pull issues)
apptainer pull docker://ghcr.io/<org>/agentic-base:latest
```

### 4. Check Partition Availability

```bash
# Check partition status
sinfo -p grete:interactive -o "%P %A %C %N"

# Check node health
sinfo -N -l -p grete:interactive
```

### 5. Check Network/Proxy Configuration

Verify Vault secrets and proxy settings:

```bash
# Check Vault secret health
VAULT_TOKEN=$(< /path/to/token) vault kv get -field=proxy_config agentic/proxy

# Test proxy connectivity from cluster nodes
kubectl exec -it <pod> -- curl -x http://proxy.gwdg.de:8080 https://example.com
```

## Common Issues and Resolutions

### Issue 1: "Submit failed: Insufficient resources"

**Cause:** Partition has no available resources or all nodes are down.

**Resolution:**

1. Check partition availability:

```bash
sinfo -p grete:interactive
```

2. If partition is down, contact GWDG HPC support.

3. If no resources, either:
   - Wait for resources to free up (check queue with `squeue -p grete:interactive`)
   - Reduce job memory/CPU requirements

### Issue 2: "Exit code 127: Command not found"

**Cause:** Apptainer not installed or not in PATH, or entrypoint script missing.

**Resolution:**

1. Verify Apptainer is available:

```bash
srun -p grete:interactive --pty apptainer --version
```

2. Check container entrypoint:

```bash
apptainer exec /shared/containers/agentic-base.sif which python3
```

3. If missing, reinstall Apptainer or rebuild container with proper entrypoint.

### Issue 3: "Exit code 126: Permission denied"

**Cause:** User lacks execute permissions or image ownership issue.

**Resolution:**

1. Check image permissions:

```bash
ls -lh /shared/containers/agentic-base.sif
```

2. Fix permissions:

```bash
chmod 755 /shared/containers/agentic-base.sif
chown root.root /shared/containers/agentic-base.sif
```

### Issue 4: Vault secrets not accessible

**Cause:** Vault token expired or malformed `VAULT_ADDR`.

**Resolution:**

1. Renew/inject fresh Vault token in agent request:

```bash
curl -X POST https://vault.gwdg.de/v1/auth/token/renew \
  -H "X-Vault-Token: <token>" -d '{"increment": "24h"}'
```

2. Verify `VAULT_ADDR` in job environment:

```bash
kubectl logs deployment/agentic-broker -n agentic | grep VAULT_ADDR
```

### Issue 5: Container fails to start (timeout)

**Cause:** Missing mount points, restrictive AppArmor profile, or compute node health issue.

**Resolution:**

1. Check required mounts:

```bash
# Shared storage, /scratch, /dev/shm must be mounted
squeue -j <job_id> -o "%.18i %.9P %.8j %.8u %.8T %.10M %.6D %R"
```

2. Disable AppArmor profile (test only):

```bash
srun --container-image=<image> --container-remaint-root
```

3. Check node health:

```bash
sinfo -R -p grete:interactive
```

4. If node has issues, drain node:

```bash
scontrol update NodeName=<node> State=DOWN Reason="maintenance"
```

## Escalation

If issue persists after above steps:

1. Collect diagnostic info:

```bash
# Job details
sacct -j <job_id> --format=ALL

# Broker logs around failure time
kubectl logs deployment/agentic-broker -n agentic --since=1h > broker-logs.txt

# Node health
sinfo -N -l -p grete:interactive > node-health.txt
```

2. Contact GWDG HPC support: hpc@gwdg.de

3. Escalate to engineering team for code-level issues.

## Prevention

- Monitor partition health with Prometheus (`slurm_jobs_active` metric)
- Set up alerts for increasing job failure rates
- Regularly validate Apptainer image accessibility
- Automate Vault token renewal before expiration
- Periodic job submission drills to test partition availability

## Metrics

Key metrics to monitor in Grafana:

- `slurm_jobs_total{partition="grete:interactive"}` - Total jobs submitted
- `slurm_jobs_active{partition="grete:interactive"}` - Currently active jobs
- `slurm_job_duration_seconds` - Job duration distribution
- `http_requests_total{endpoint="/api/jobs",status_code=~"5.."}` - 5xx errors on job submission

## Related Documentation

- [Slurm REST API documentation](https://slurm.schedmd.com/rest_api.html)
- [Apptainer user guide](https://apptainer.org/docs/user/main/)
- [Vault API documentation](https://www.vaultproject.io/api-docs)