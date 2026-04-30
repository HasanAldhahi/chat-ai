# Runbook: Security Incident Response (Task 5.5 Production Readiness)

## Overview

This runbook provides procedures for handling security incidents in the agentic layer. All security incidents must be reported to GWDG security team per institutional policy.

## Severity Levels

### P0 - Critical (Immediate Action Required)
- Active data breach or exfiltration
- Confirmed unauthorized access to production systems
- Ransomware or malware detected in production
- Credentials exposed publicly (GitHub, logs, etc.)

### P1 - High (Action Within 1 Hour)
- Potential unauthorized access (failed auth attempts spike)
- Suspicious审计日志 entries
- Security vulnerability in production code
- Secrets suspected to be compromised but not confirmed

### P2 - Medium (Action Within 4 Hours)
- Security misconfiguration detected
- Outdated dependencies with known CVEs
- Unusual but not immediately malicious activity
- Failed penetration test finding

### P3 - Low (Action Within 1 Day)
- Minor security finding (CWE, weak config)
- Documentation/security policy gap
- False positive from security tool

## Initial Response (All Severities)

### 1. Triage and Classify

```bash
# Check recent security-related logs
kubectl logs deployment/agentic-broker -n agentic --tail=1000 | grep -E "(auth|error|security|unauthorized)"

# Check Slurm logs for unusual job submissions
kubectl logs deployment/agentic-broker -n agentic | grep "slurm" | grep -i error

# Check audit log (UAT metrics)
kubectl exec -it <pod> -n agentic -- cat /tmp/agentic_audit.jsonl | tail -50
```

Classify based on:
- Active vs historical incident
- Data exposure risk
- System accessibility
- User impact

### 2. Containment (P0/P1 Only)

#### Block suspicious IPs

Create NetworkPolicy to block attacker IPs:

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: block-attacker-ips
  namespace: agentic
spec:
  podSelector: {}
  policyTypes:
  - Egress
  - Ingress
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
        - <ATTACKER_IP>/32
EOF
```

#### Rotate credentials

```bash
# Rotate Vault tokens
VAULT_TOKEN=$(< /path/to/bootstrap-token) \
  curl -X POST https://vault.gwdg.de/v1/auth/token/revoke-accessor \
    -H "X-Vault-Token: $VAULT_TOKEN" \
    -d '{"accessor": "<accessor>"}'

# Rotate API secrets
kubectl create secret generic new-secrets --from-literal=token=$(openssl rand -hex 32) -n agentic
kubectl set env deployment/agentic-broker SECRET_NAME=new-secrets -n agentic
kubectl rollout restart deployment/agentic-broker -n agentic
```

#### Stop service if needed

```bash
# Scale to zero if active attack
kubectl scale deployment agentic-broker --replicas=0 -n agentic

# Or pause RollingUpdate
kubectl rollout pause deployment/agentic-broker -n agentic
```

### 3. Notify Stakeholders

Create incident channel and notify:

- GWDG security team: security@gwdg.de
- Engineering on-call: eng-oncall@gwdg.de
- Product owner: agentic-lead@gwdg.de

## P0 - Critical Incident Procedure

### Immediate Actions (0-15 min)

1. Isolate affected systems:

```bash
# Stop all agent sessions: cancel Slurm jobs
for job_id in $(squeue -h -u agentic-user -o "%A"); do
  scancel $job_id
done

# Scale broker to zero
kubectl scale deployment agentic-broker --replicas=0 -n agentic
```

2. Collect forensic evidence:

```bash
# Capture pod logs before deletion
kubectl get pods -n agentic -l app=agentic-broker

for pod in $(kubectl get pods -n agentic -l app=agentic-broker -o name); do
  kubectl logs $pod -n agentic > logs/$(basename $pod)-$(date +%s).txt
done

# Capture network traffic
tcpdump -i any -w agentic-incident-$(date +%s).pcap host <attacker-ip>

# Audit log snapshot
kubectl cp <pod>:/tmp/agentic_audit.jsonl ./agentic_audit_backup.jsonl
```

3. Document timeline:

```bash
# Record when incident detected, actions taken
echo "Incident detected at $(date)" | tee incident-log.txt
echo "System isolated at $(date)" >> incident-log.txt
```

### Investigation (15 min - 2 hours)

4. Analyze attack vector:

- Check authentication logs for brute force attempts
- Check Slurm job submissions for suspicious containers
- Review Vault access logs for secret reads
- Inspect network logs for exfiltration signs

5. Determine data impact:

- Check if secrets, user data, or source code accessed
- Review Slurm containers for data left behind
- Check audit logs for missing or unusual entries

### Recovery (2-8 hours)

6. Wipe and rebuild:

```bash
# Rotate all secrets
vault kv patch -mount=kv agentic/proxy -token=$(openssl rand -hex 32)

# Force redeployment with new image
kubectl set image deployment/agentic-broker \
  agentic-broker=ghcr.io/<org>/agentic-broker:post-incident -n agentic

kubectl rollout restart deployment/agentic-broker -n agentic
```

7. Enable hardening:

- Enforce MFA for all admin access
- Rate limit API endpoints more aggressively
- Enable additional security monitoring

8. Communicate:

- GWDG security team status updates hourly
- Notify users if data was exposed

## P1 - High Incident Procedure

### Actions (0-1 hour)

1. Pattern analysis:

```bash
# Check for auth anomalies (e.g., same user from multiple IPs)
kubectl logs deployment/agentic-broker -n agentic \
  | awk '/X-User/ {print $NF}' | sort | uniq -c | awk '$1 > 10'

# Check for Slurm job anomalies
kubectl logs deployment/agentic-broker -n agentic \
  | grep "slurm" | awk '{print $(NF-2)}' | sort | uniq -c | awk '$1 > 5'
```

2. Tighten security:

```bash
# Enable stricter rate limiting
kubectl set env deployment/agentic-broker \
  AGENTIC_AUTH_RATE_PER_USER=5 \
  AGENTIC_AUTH_RATE_WINDOW_S=60 -n agentic

kubectl rollout restart deployment/agentic-broker -n agentic
```

3. Investigate source:

- Check GitHub recent commits for accidental secret exposure
- Review CI/CD logs for credential leakage
- Audit user accounts in GWDG SSO

### Recovery (1-4 hours)

4. If confirmed attack, escalate to P0

5. If false positive, tune monitoring

## P2/P3 - Medium/Low Incident Procedure

1. Document finding: CVE ID, affected component, exploitability

2. Risk assessment:

```bash
# Check if vulnerable code in production
grep -r "<vulnerable-library>" /app/
```

3. Remediation:

- Patch dependencies in `requirements.txt`
- Deploy updated container image
- Run security scanner: `pip-audit`, `safety check`

4. Document for post-incident review

## Post-Incident Review (All Severities)

Within 1 week of incident resolution:

1. Root cause analysis:
   - Why did incident happen?
   - What controls failed?
   - How was it detected?

2. Action items:
   - Update runbooks
   - Additional monitoring/alerts
   - Security training if human error
   - Code review process improvements

3. Documentation:
   - Incident report (GWDG template)
   - Update security policy
   - Share lessons learned with team

## Monitoring and Prevention

### Security Alerts to Setup

```yaml
# Alertmanager rules
groups:
  - name: security
    rules:
      - alert: UnauthorizedAccessAttemptsHigh
        expr: rate(http_requests_total{status_code=401}[5m]) > 10
        for: 5m
        annotations:
          summary: "High unauthorized access attempts"

      - alert: VaultTokenExpiringSoon
        expr: vault_token_ttl_remaining < 21600  # < 6 hours
        annotations:
          summary: "Vault token expiring soon"

      - alert: SlurmJobSubmissionAnomaly
        expr: rate(slurm_jobs_total[5m]) > 10
        annotations:
          summary: "Unusual Slurm job submission rate"

      - alert: SuspiciousAuditLogEntries
        expr: count(increase(audit_log_entries{level="error"}[1h])) > 10
        annotations:
          summary: "Multiple errors in audit log"
```

### Regular Security Audits

- Monthly dependency vulnerability scan: `pip-audit`
- Quarterly penetration test of API endpoints
- Bi-annual GWDG security policy review
- Annual incident response drill

### Documentation

Maintain up-to-date:
- Security policy document (GWDG template)
- Incident communication plan (who to notify)
- Escalation matrix (who to contact for each severity)

## Escalation Matrix

| Severity | Notify Immediately | Escalate After | Contact |
|----------|-------------------|----------------|---------|
| P0 | GWDG security, CEO | N/A | security@gwdg.de |
| P1 | GWDG security, eng-lead | 4 hours | security@gwdg.de |
| P2 | eng-lead | 8 hours | eng-lead@gwdg.de |
| P3 | eng-lead | 24 hours | eng-lead@gwdg.de |

## Legal/Compliance

- All P0/P1 incidents reported to GWDG data protection officer within 72 hours
- Retain incident logs for 1 year per GWDG policy
- Filed incident reports accessible for audit

## Credits

Based on:
- GWDG security response policy (version 2.3)
- NIST Cybersecurity Framework
- OWASP Incident Response Guide

## Related Documentation

- [GWDG security policies](https://gwdg.de/security)
- [OWASP incident response](https://owasp.org/www-community/Incident_Response_Cheat_Sheet)
- [Vault security best practices](https://www.vaultproject.io/docs/security)