# Runbook: Vault Unavailability (Task 5.5 Production Readiness)

## Overview

This runbook provides procedures for handling Vault unavailability in the agentic layer. Vault is critical for storing secrets (API keys, tokens, proxy config) used by agent sessions.

## Symptoms

- Job submission fails with "Vault token invalid" or "Vault unreachable"
- Agent sessions fail to start with "secret_not_found"
- Metrics show increasing `vault_request_errors`
- Grafana alerts: "Vault connection failure"

## Diagnosis

### 1. Check Vault Health

```bash
# Check Vault health (Unsealed, standby, HA status)
curl https://vault.gwdg.de/v1/sys/health

# Check if specific secret exists (requires token)
VAULT_TOKEN=$(< /path/to/token) \
  curl -H "X-Vault-Token: $VAULT_TOKEN" \
    https://vault.gwdg.de/v1/kv/data/agentic/proxy
```

### 2. Check Broker Logs

```bash
kubectl logs deployment/agentic-broker -n agentic | grep -i vault

# Look for errors like:
# - "VaultError: connection refused"
# - "VaultError: invalid token"
# - "VaultError: permission denied"
```

### 3. Check Network Connectivity

```bash
# Test Vault reachability from broker pod
kubectl exec -it <pod> -n agentic -- curl -k https://vault.gwdg.de/v1/sys/health

# Test DNS resolution
kubectl exec -it <pod> -n agentic -- nslookup vault.gwdg.de
```

### 4. Check Token Validity

```bash
# Check token TTL
VAULT_TOKEN=$(< /path/to/token) \
  curl -H "X-Vault-Token: $VAULT_TOKEN" \
    https://vault.gwdg.de/v1/auth/token/lookup-self

# Renew token if expired
curl -X POST https://vault.gwdg.de/v1/auth/token/renew \
  -H "X-Vault-Token: $VAULT_TOKEN" -d '{"increment": "24h"}'
```

### 5. Check Vault Service Status

```bash
# Get Vault pods
kubectl get pods -n vault -l app=vault

# Check Vault logs
kubectl logs -f deployment/vault -n vault

# Check Vault leader election (HA)
kubectl exec -it deployment/vault -n vault -- vault operator raft list-peers
```

## Common Issues and Resolutions

### Issue 1: Vault Sealed

**Cause:** Vault was sealed for maintenance or during OOM.

**Resolution:**

⚠️ Contact GWDG security team - unsealing requires unseal keys stored securely.

Once unsealed, verify:

```bash
curl https://vault.gwdg.de/v1/sys/health
# Should return: {"initialized":true,"sealed":false,...}
```

### Issue 2: Vault Token Expired

**Cause:** Token TTL exceeded or token revoked.

**Resolution:**

1. Use bootstrap token to get new service token:

```bash
VAULT_TOKEN=$(< /path/to/bootstrap-token) \
  curl -X POST https://vault.gwdg.de/v1/auth/token/create \
    -H "X-Vault-Token: $VAULT_TOKEN" \
    -d '{"ttl": "72h", "policies": ["agentic"]}' \
    | jq -r '.auth.client_token'
```

2. Store new token securely:

```bash
kubectl create secret generic vault-token \
  --from-literal=token=<new-token> -n agentic
```

3. Rotate service tickets by redeploying broker:

```bash
kubectl rollout restart deployment/agentic-broker -n agentic
```

### Issue 3: Network Connectivity Issues

**Cause:** DNS resolution failure, network partition, firewall rules.

**Resolution:**

1. Test DNS:

```bash
kubectl exec -it <pod> -n agentic -- nslookup vault.gwdg.de

# If fails, check CoreDNS:
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

2. Test Vault IP (bypass DNS):

```bash
kubectl exec -it <pod> -n agentic -- curl -k https://<VAULT_IP>:8200/v1/sys/health
```

3. Check network policies:

```bash
kubectl get networkpolicies -n agentic
# Ensure egress to vault.gwdg.de:8200 allowed
```

### Issue 4: Permission Denied / Secret Missing

**Cause:** Policy misconfiguration, secret path moved, or wrong kv version.

**Resolution:**

1. Check secret path and kv version:

```bash
# Check KV v1 vs v2
VAULT_TOKEN=$(< /path/to/token) \
  curl -H "X-Vault-Token: $VAULT_TOKEN" \
    https://vault.gwdg.de/v1/sys/mounts

# Secret path may be:
# - /v1/secret/data/agentic/proxy  (KV v2)
# - /v1/kv/data/agentic/proxy     (KV v2)
# - /v1/secret/agentic/proxy       (KV v1)
```

2. Create missing secret:

```bash
VAULT_TOKEN=$(< /path/to/token) \
  curl -X PUT https://vault.gwdg.de/v1/kv/data/agentic/proxy \
    -H "X-Vault-Token: $VAULT_TOKEN" \
    -d '{"data":{"proxy_url":"http://proxy.gwdg.de:8080","proxy_user":"user","proxy_pass":"pass"}}'
```

3. Verify broker uses correct secret path:

```bash
kubectl env deployment/agentic-broker --list -n agentic | grep VAULT
```

### Issue 5: Vault High Load / Timeout

**Cause:** Too many concurrent requests, insufficient Vault resources.

**Resolution:**

1. Check Vault metrics:

```bash
curl https://vault.gwdg.de/v1/v1/sys/metrics | jq
```

2. Scale Vault horizontally (HA):

```bash
kubectl scale statefulset vault --replicas=3 -n vault
```

3. Enable request caching in broker:

```bash
kubectl set env deployment/agentic-broker VAULT_CACHE_ENABLED=true -n agentic
```

4. Add rate limiting to broker Vault client:

```python
# In vault client code
vault_client = hvac.Client(
    url=os.getenv("VAULT_ADDR"),
    token=os.getenv("VAULT_TOKEN"),
    session=RetrySession(total=3, backoff_factor=0.5)
)
```

## Temporary Workarounds

### Use Environment Variables

If Vault temporarily unavailable, inject secrets via env vars (not recommended for long-term):

```bash
kubectl set env deployment/agentic-broker \
  PROXY_URL=http://proxy.gwdg.de:8080 \
  PROXY_USER=user PROXY_PASS=pass -n agentic

kubectl rollout restart deployment/agentic-broker -n agentic
```

⚠️ These values appear in pod specs - rotate secret in Vault ASAP.

### Use Secret Object

Create K8s Secret object as backup:

```bash
kubectl create secret generic proxy-secrets \
  --from-literal=proxy_url=http://proxy.gwdg.de:8080 \
  --from-literal=proxy_user=user \
  --from-literal=proxy_pass=pass -n agentic
```

Mount into pod if Vault fails.

## Recovery After Vault Restored

Once Vault is back online:

1. Verify Vault health:

```bash
curl https://vault.gwdg.de/v1/sys/health
```

2. Rotate short-lived tokens:

```bash
VAULT_TOKEN=$(< /path/to/bootstrap-token) \
  curl -X POST https://vault.gwdg.de/v1/auth/token/renew \
    -H "X-Vault-Token: $VAULT_TOKEN" -d '{"increment": "72h"}'
```

3. Restart broker to refresh tokens:

```bash
kubectl rollout restart deployment/agentic-broker -n agentic
```

4. Verify secrets accessible:

```bash
kubectl logs deployment/agentic-broker -n agentic | tail -20
```

5. Clean up temporary workarounds (env vars, K8s secrets).

## Escalation

If Vault remains unavailable for > 30 minutes:

1. Contact GWDG security team: vault@gwdg.de
2. Document incident:
   - Timestamp of failure
   - Error messages from logs
   - Any config changes made (env vars, secrets)
3. Post-incident review:
   - Why did Vault go down?
   - Why did fallback not work?
   - Improve monitoring/alerting

## Prevention

- Set up Vault HA replication (multi-node cluster)
- Cache frequently accessed secrets with TTL
- Implement secret rotation before expiry
- Run regular backup and restore tests
- Set up alerts for:
  - `vault_request_errors` (threshold > 0)
  - `vault_token_ttl_remaining` (alert < 6 hours)
  - Vault pod OOMKilled
  - Vault sealed status change

## Metrics

Key metrics to monitor:

- `vault_request_errors` - Vault API errors
- `vault_token_ttl_remaining` - Time until token expiry
- `vault_seal_status` - Is Vault sealed?
- `http_requests_total{endpoint="/api/vault/...",status_code=~"5.."}` - 5xx from Vault client

## Related Documentation

- [Vault operational guide](https://www.vaultproject.io/docs/operating)
- [Vault HA setup](https://www.vaultproject.io/docs/enterprise/ha)
- [Vault API documentation](https://www.vaultproject.io/api-docs)