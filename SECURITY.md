# Security Policy

## Supported Versions

Security updates are provided for the latest stable release line.

| Version | Supported |
| --- | --- |
| v1.0.x | Yes |
| < v1.0.0 | No |

## Reporting a Vulnerability

If you discover a security issue, do not open a public issue with exploit details.

Please report responsibly with:

- A clear description of the issue
- Reproduction steps
- Impact assessment
- Suggested mitigation (if available)

Use one of the following channels:

- Security contact in repository settings
- Private maintainer contact used for release operations

## Response Targets

- Initial acknowledgement: within 72 hours
- Triage status update: within 7 days
- Fix timeline: based on severity and exploitability

## Disclosure Process

1. Report is received and triaged.
2. Affected versions and components are validated.
3. A patch is prepared and tested.
4. Coordinated disclosure is published with remediation guidance.

## Security Baseline

Prady OS v1.0.0 applies these baseline controls:

- Policy-gated agent actions in platform runtime
- Service-level health and diagnostics endpoints
- Signed release artifact workflow with checksums
- CI validation with strict type/lint/test gates

## Hardening Recommendations

- Keep secrets out of source and rotate credentials regularly.
- Restrict service exposure to trusted networks.
- Run only required ports and disable unused services.
- Monitor logs for unusual tool/action patterns.
- Pin and audit dependencies as part of release checks.

## Scope Notes

This policy covers first-party Prady OS components in this repository.
Third-party upstream mirrors and vendored projects follow their own disclosure policies.

**Example Policy:**
```yaml
deny:
  - action: shell-execute
    reason: "No direct shell access"
  - action: file-delete
    reason: "Requires approval"
    approval_required: true
allow:
  - action: mouse-click
  - action: screenshot
```

**Detection:**
- Monitor for denied actions in screen-agent logs
- Alert on policy violations
- Review approval decisions regularly

---

#### Scenario 4: Denial of Service (DoS)

**Attack:** Attacker floods redis or model-gateway with requests.

**Mitigation:**
1. Rate limiting on model-gateway (per model, per hour)
2. Task queue depth monitoring
3. Approval queue timeout (prevents stuck tasks)
4. Redis memory limits and eviction policy

**Detection:**
- Monitor Redis memory: `redis-cli INFO memory`
- Alert if task queue depth > 100
- Alert if approval queue > 10 for > 5 minutes

---

#### Scenario 5: Session Hijacking

**Attack:** Attacker intercepts or reuses session tokens.

**Mitigation:**
1. Sessions stored in Redis (in-memory, encrypted in transit via HTTPS in production)
2. Session timeout: 1 hour (LUMYN_SESSION_TIMEOUT)
3. Session IDs are cryptographically random (not sequential)
4. No session persistence across restarts (by design)

**Production Enhancement:**
- Use HTTPS for all service-to-service communication
- Add session token signing (JWT with HS256)
- Implement session revocation list (Redis)

---

#### Scenario 6: Malicious Model Output

**Attack:** Cloud API (OpenAI, Anthropic) returns malicious content (e.g., shell commands).

**Mitigation:**
1. Lumyn agent validates tool calls before execution
2. ReAct loop enforces structured output parsing
3. Tool validation before execution (no direct string execution)
4. Output logged for audit and review

**Example Safe Tool Call:**
```python
# UNSAFE: Direct execution
bash(f"curl {user_url}")

# SAFE: Validated tool call
url = parse_url(user_input)  # Validation
if not url.is_trusted():
    raise PolicyError("Untrusted URL")
result = browser_navigate(url)  # Controlled tool
```

---

### Attack Tree

```
┌── Compromise Kryos System
    ├── [1] Exploit Input Validation
    │   ├── Prompt Injection → Lumyn (ReAct validates) → MITIGATED
    │   ├── File Path Traversal → screen-agent (policy gates) → MITIGATED
    │   └── SQL Injection → Redis (no SQL, RESP protocol) → N/A
    │
    ├── [2] Steal API Keys
    │   ├── From Environment → Keys in .env, not logged → MITIGATED
    │   ├── From Memory → Process-level isolation (containers) → MITIGATED
    │   ├── From Network → Encrypt in transit (HTTPS in prod) → MITIGATED
    │   └── From Logs → Keys never logged → MITIGATED
    │
    ├── [3] Bypass Approval Workflow
    │   ├── Session Hijacking → Session timeouts, HTTPS → MITIGATED
    │   ├── Token Replay → Random session IDs → MITIGATED
    │   └── Approval Timeout → Explicit human decision → MITIGATED
    │
    ├── [4] Unauthorized Desktop Access
    │   ├── Unpatched X11 → DISPLAY isolation → MITIGATED
    │   ├── Policy Bypass → Policy engine validates all → MITIGATED
    │   └── Sudo Escalation → No sudo in containers → MITIGATED
    │
    ├── [5] Redis Compromise
    │   ├── Network Access → No external network exposure → MITIGATED
    │   ├── Authentication → Trusted network (no password required) → ACCEPTED RISK
    │   └── Data Exposure → Sessions in-memory (ephemeral) → ACCEPTED RISK
    │
    └── [6] Supply Chain Attack
        ├── Malicious Dependency → Dependency audit (Phase B) → MITIGATED
        ├── Docker Image Tampering → Image signing (future) → FUTURE
        └── GitHub Actions Compromise → Branch protection, code review → MITIGATED
```

---

## Trust Boundaries

### Zone 1: User Input (Untrusted)

**Boundary:** Lumyn agent receives user goals/queries.

**Controls:**
- Input validation (length, charset)
- ReAct loop enforces structured output
- Tool call validation before execution
- Audit logging of all user input

---

### Zone 2: Agent Layer (Semi-Trusted)

**Boundary:** Lumyn, workflow-engine, screen-agent.

**Controls:**
- Service-to-service authentication (future: mTLS)
- Rate limiting per service
- Audit trail for all operations
- Policy gating for destructive actions

---

### Zone 3: External APIs (Semi-Trusted)

**Boundary:** OpenAI, Anthropic, Ollama.

**Controls:**
- API key rotation (monthly)
- Circuit breaker for API failures
- Response validation (no injection)
- Cost monitoring (alert on spike)

---

### Zone 4: System Services (Trusted)

**Boundary:** Redis, Docker network.

**Controls:**
- Network isolation (no public exposure)
- Resource limits (memory, CPU)
- Restart policies (fail-safe)
- Health checks on all services

---

## Security Controls

### 1. API Gateway (model-gateway)

**Purpose:** Single entry point for all LLM requests.

**Controls:**
- API key management (per model, per environment)
- Rate limiting (100 req/min per model)
- Request/response validation (JSON schema)
- Audit logging (all queries, responses, latencies)
- Error handling (no credential leaks in errors)

**Implementation:**
```python
@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    # Validate request
    validate_request(req)
    
    # Log request (no sensitive data)
    audit_log.info(f"chat_completions: {req.model}, tokens={len(req.messages)}")
    
    # Route based on policy
    response = await route_to_model(req)
    
    # Log response (metadata only)
    audit_log.info(f"response: {response.model}, tokens={response.usage.total_tokens}")
    
    return response
```

---

### 2. Approval Workflow (workflow-engine)

**Purpose:** Require human approval for high-risk tasks.

**Controls:**
- Task classification (cost, destructive, sensitive)
- Approval queue with timeout (300s default)
- Audit logging of approval decisions
- Auto-approval configurable

**Approval Triggers:**
- File deletion
- Network requests (HTTP POST/PUT/DELETE)
- Email/message sending
- Large-scale operations (>10 subtasks)
- Cost > $1.00

**Implementation:**
```python
async def execute_task(task: TaskRequest):
    # Classify risk
    risk_level = classify_task(task)
    
    if risk_level in ["high", "destructive"]:
        # Require approval
        approval = ApprovalRecord(
            task_id=task.id,
            risk_level=risk_level,
            timeout_at=now() + APPROVAL_TIMEOUT_SECONDS
        )
        approvals_queue.append(approval)
        await wait_for_approval(approval)
    
    # Execute
    result = await execute(task)
    return result
```

---

### 3. Policy Gating (screen-agent)

**Purpose:** Control desktop automation actions with security policies.

**Controls:**
- Whitelist/blacklist actions
- Parameter validation (paths, commands)
- Real-time policy evaluation
- Detailed audit logging

**Policy Example:**
```yaml
# /app/config/policy.yaml

# Whitelist safe actions
allow:
  - action: screenshot
  - action: mouse-click
    constraints:
      target_region: screen  # not outside screen bounds
  - action: browser-navigate
    constraints:
      domain_whitelist:
        - github.com
        - news.ycombinator.com

# Blacklist dangerous actions
deny:
  - action: shell-execute
    reason: "No direct shell access"
  - action: file-delete
    reason: "Destructive operation"
  - action: sudo-run
    reason: "No privilege escalation"
  - action: read-keychain
    reason: "No credential access"
```

---

### 4. Audit Trail

**Purpose:** Create immutable record of all operations for forensics.

**Implementation:**
```json
{
  "timestamp": "2025-01-15T14:30:45.123Z",
  "level": "INFO",
  "service": "workflow-engine",
  "event": "task_executed",
  "task_id": "task_abc123",
  "session_id": "sess_user_123",
  "user_goal": "[redacted]",
  "subtasks_executed": 3,
  "approval_required": true,
  "approval_status": "approved",
  "result": "success",
  "duration_ms": 2345
}
```

**Audit Logs Locations:**
- `/ai-core/model-gateway/logs/queries.jsonl` — LLM queries
- `/orchestration/workflow-engine/logs/activities.jsonl` — Task execution
- `/automation/screen-agent/logs/actions.jsonl` — Desktop actions
- `/agents/lumyn/logs/sessions.jsonl` — Conversations

**Retention:** 90 days (configurable)

---

### 5. Secrets Management

**Current State (Development):**
- API keys in `.env` (gitignored)
- Keys injected as environment variables
- No key rotation automated

**Production Requirements:**
- Use AWS Secrets Manager or HashiCorp Vault
- Automatic key rotation (monthly)
- Encryption at rest and in transit (HTTPS)
- Audit logging for key access
- Short-lived credentials (STS tokens)

---

## Hardening Checklist

### Development Environment

- [ ] `.env` file created from `.env.example`
- [ ] `OPENAI_API_KEY` set and tested
- [ ] `ANTHROPIC_API_KEY` set (optional, for fallback)
- [ ] `DISPLAY` set (for screen-agent)
- [ ] `GATEWAY_ROUTING_MODE=local-first` (for Ollama development)
- [ ] No keys committed to Git

### Production Deployment

#### Pre-Deployment

- [ ] All tests passing: `make test-all`
- [ ] Environment validation: `make doctor`
- [ ] Configuration validation: `make validate`
- [ ] No debug logging: `LOG_LEVEL=WARNING`
- [ ] Redis persistence enabled
- [ ] Backups configured and tested

#### Container Security

- [ ] All Dockerfiles use non-root user
- [ ] All base images scanned for vulnerabilities
- [ ] All dependencies pinned (no floating versions)
- [ ] No secrets in Docker images
- [ ] Image signing configured

#### Network Security

- [ ] Services not exposed to public internet
- [ ] Localhost-only ports: `127.0.0.1:port:port`
- [ ] HTTPS enforced for external APIs
- [ ] mTLS configured for inter-service communication (future)
- [ ] Firewall rules restrict access

#### Access Control

- [ ] API keys rotated monthly
- [ ] Service-to-service authentication enabled
- [ ] User approval workflow enforced
- [ ] Audit logging enabled and monitored
- [ ] Session timeouts configured (1 hour)

#### Monitoring & Alerting

- [ ] Prometheus metrics exported
- [ ] ELK logging aggregation enabled
- [ ] Alerts configured for:
  - [ ] Redis memory > 80%
  - [ ] API errors > 5% of requests
  - [ ] Approval queue depth > 10 for > 5 minutes
  - [ ] Unauthorized actions (policy denials)
  - [ ] API key failures (potential compromise)

#### Incident Response

- [ ] Incident response plan documented
- [ ] Escalation contacts listed
- [ ] Log retention configured (90 days minimum)
- [ ] Backup and restore procedures tested
- [ ] Disaster recovery plan in place

---

## Incident Response

### Detection & Alerting

#### Alert 1: Unauthorized Action (screen-agent)

```
Event: ACTION_DENIED
Level: CRITICAL
Service: screen-agent
Action: file-delete /etc/passwd
Policy: deny (destructive)
```

**Response:**
1. Isolate screen-agent: `docker-compose stop screen-agent`
2. Review session: `docker-compose logs screen-agent | grep session_id`
3. Check audit trail: `grep session_id ./automation/screen-agent/logs/actions.jsonl`
4. Investigate user: Review user's recent actions and goals
5. Restart screen-agent: `docker-compose up -d screen-agent`

---

#### Alert 2: API Key Failure (model-gateway)

```
Event: API_ERROR
Level: CRITICAL
Service: model-gateway
Error: 401 Unauthorized (OpenAI API)
```

**Response:**
1. Verify API key: `env | grep OPENAI_API_KEY`
2. Test key with curl: `curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models`
3. Check API provider dashboard for suspicious activity
4. Rotate key immediately if compromised
5. Update .env and restart: `export OPENAI_API_KEY=sk-new...; docker-compose restart model-gateway`

---

#### Alert 3: Redis Memory Critical (redis)

```
Event: MEMORY_HIGH
Level: WARNING
Service: redis
Memory: 95% of limit
```

**Response:**
1. Check memory usage: `docker-compose exec redis redis-cli INFO memory`
2. Identify large keys: `docker-compose exec redis redis-cli --bigkeys`
3. Check task queue depth: `docker-compose exec redis redis-cli LLEN tasks:queue`
4. Option A: Clear old sessions (if safe): `docker-compose exec redis redis-cli EVAL "return redis.call('del', ...)" 0`
5. Option B: Increase Redis memory limit in docker-compose.yml
6. Option C: Migrate to managed Redis (production)

---

#### Alert 4: Approval Queue Backlog (workflow-engine)

```
Event: APPROVAL_BACKLOG
Level: WARNING
Service: workflow-engine
Pending: 15 approvals > 5 minutes
```

**Response:**
1. Review pending approvals: `docker-compose logs workflow-engine | grep "pending"`
2. Assess risk: High? Destructive? Low? Rate each by risk
3. For low-risk approvals, approve them: `curl -X POST http://localhost:11431/task/ID/approve -d '{"decision": "approve"}'`
4. For high-risk approvals, investigate first
5. For stuck approvals (timeout reached), auto-approve or reject: `curl -X POST ... -d '{"decision": "reject", "reason": "timeout"}'`

---

### Containment & Recovery

#### Immediate Actions (T+0 to T+15 minutes)

1. **Isolate Compromised Service:**
   ```bash
   docker-compose stop <service>
   ```

2. **Preserve Evidence:**
   ```bash
   docker-compose logs <service> > /tmp/incident-logs.txt
   docker cp redis-container:/data/dump.rdb /tmp/incident-redis.rdb
   ```

3. **Notify Team:**
   - Post to #security Slack channel
   - Create incident ticket (title, timeline, impact)

4. **Assess Blast Radius:**
   - Which services affected?
   - Which users affected?
   - What data exposed?

---

#### Remediation (T+15 to T+60 minutes)

1. **Root Cause Analysis:**
   - Review audit logs: Was input validation bypassed?
   - Check policy settings: Was policy misconfigured?
   - Inspect code: Any recent changes?

2. **Implement Fix:**
   - Patch input validation
   - Tighten policy rules
   - Update dependencies (if vulnerable)

3. **Test Fix:**
   - Run full test suite: `make test-all`
   - Specifically test vulnerable path
   - Deploy to staging first

4. **Deploy Fix:**
   ```bash
   docker-compose up -d --build
   docker-compose ps  # Verify all healthy
   ```

---

#### Post-Incident (T+60 minutes to T+24 hours)

1. **Write Incident Report:**
   - Timeline
   - Root cause
   - Impact assessment
   - Mitigation steps
   - Prevention measures

2. **Communication:**
   - Notify affected users
   - Publish post-mortem (internal wiki)
   - Schedule team retrospective

3. **Prevention:**
   - Update security checklist
   - Add test case for vulnerability
   - Update runbook
   - Monitor for recurrence

---

## Compliance

### Security Standards

Prady OS v2 aligns with:

- **OWASP Top 10:** Input validation, access control, logging, secrets management
- **CWE (Common Weakness Enumeration):** CWE-89 (SQL injection), CWE-94 (code injection), CWE-352 (CSRF)
- **NIST Cybersecurity Framework:** Identify, Protect, Detect, Respond, Recover

### Data Protection

**Data Classification:**
- **Public:** Model names, service status, documentation
- **Internal:** Audit logs, session IDs, task descriptions
- **Sensitive:** API keys, user credentials, user goals, PII
- **Confidential:** Redis data, internal metrics

**Retention:**
- Audit logs: 90 days
- Session data: 1 hour (ephemeral in Redis)
- Learnings: Indefinite (model optimization)

**Deletion Policy:**
- Automatic deletion after retention period
- Manual deletion on user request (GDPR)
- Secure deletion (overwrite 3x before reclaim)

---

## Security Updates

### Dependency Scanning

Automated scanning via GitHub Actions (when implemented):

```yaml
# .github/workflows/security.yml
- name: Scan Python dependencies
  run: |
    pip install safety
    safety check --json > safety-report.json

- name: Scan Node dependencies
  run: |
    npm audit --json > npm-audit-report.json

- name: Upload to repository
  uses: actions/upload-artifact@v3
  with:
    name: security-reports
    path: |
      safety-report.json
      npm-audit-report.json
```

### Vulnerability Response

1. **Detection:** Security scanner identifies CVE
2. **Assessment:** Determine if Kryos is affected
3. **Planning:** Plan mitigation (patch, workaround, accept risk)
4. **Implementation:** Apply fix (usually dependency update)
5. **Testing:** Run full test suite
6. **Deployment:** Deploy fix to production
7. **Communication:** Notify stakeholders

---

## Contacts & Resources

### Security Contacts

- **Security Lead:** [TBD]
- **Incident Response:** security@kryos.dev
- **Vulnerability Disclosure:** security@kryos.dev

### External Resources

- **OWASP:** https://owasp.org/
- **CWE:** https://cwe.mitre.org/
- **NIST:** https://www.nist.gov/cyberframework
- **Docker Security:** https://docs.docker.com/engine/security/

---

**Document Owner:** Security Team  
**Last Reviewed:** 2025-01-15  
**Next Review:** 2025-04-15  
**Classification:** SENSITIVE
