# Prady OS v2 Runbook

**Document Version:** 1.0  
**Last Updated:** 2025  
**Status:** Production Ready  

## Quick Start

### Local Development Setup

```bash
# Clone and setup
git clone https://github.com/kryos/prady-os.git
cd prady-os

# Create .env from template
cp .env.example .env

# Start all services
make dev-up

# Verify all services are healthy
curl http://localhost:11430/healthz  # model-gateway
curl http://localhost:11431/healthz  # workflow-engine
curl http://localhost:11433/healthz  # screen-agent
curl http://localhost:11436/healthz  # lumyn-agent

# Run end-to-end tests
make test-e2e

# View logs
make logs
```

### Production Deployment

```bash
# Verify environment is production-ready
make doctor

# Run comprehensive validation
make validate

# Start services in production mode
LOG_LEVEL=WARNING docker-compose up -d

# Monitor startup
docker-compose ps
docker-compose logs -f

# Verify all services healthy
docker-compose exec redis redis-cli ping
curl http://model-gateway:8000/healthz
curl http://workflow-engine:8000/healthz
curl http://screen-agent:8000/healthz
curl http://lumyn-agent:8000/healthz
```

---

## Table of Contents

1. [Operational Tasks](#operational-tasks)
2. [Troubleshooting](#troubleshooting)
3. [Monitoring & Alerting](#monitoring--alerting)
4. [Maintenance](#maintenance)
5. [Security](#security)
6. [Disaster Recovery](#disaster-recovery)

---

## Operational Tasks

### Starting Services

#### Local Development

```bash
make dev-up
```

This command:
1. Starts Redis
2. Waits for Redis health check (10s max)
3. Starts model-gateway with 15s startup timeout
4. Waits for model-gateway health check
5. Starts workflow-engine, screen-agent, lumyn-agent
6. Waits for all health checks

#### Production

```bash
# Ensure .env is configured
cat .env

# Start with restart policy
docker-compose up -d

# Monitor logs for errors
docker-compose logs -f --tail 50
```

### Stopping Services

#### Graceful Shutdown

```bash
make dev-down
```

This ensures:
1. Pending approvals are logged
2. Redis data is flushed (optional)
3. All containers stopped
4. No orphaned processes

#### Emergency Shutdown

```bash
docker-compose kill
docker-compose rm -f
```

Use only if graceful shutdown fails.

### Viewing Logs

#### All Services

```bash
make logs
```

#### Specific Service

```bash
docker-compose logs -f <service>  # e.g., workflow-engine
```

#### Follow Real-Time

```bash
docker-compose logs -f --tail 100
```

#### Search Logs

```bash
docker-compose logs | grep "ERROR\|WARN"
```

### Health Checks

#### Quick Health

```bash
# Test all endpoints
curl http://localhost:11430/healthz  # model-gateway
curl http://localhost:11431/healthz  # workflow-engine
curl http://localhost:11433/healthz  # screen-agent
curl http://localhost:11436/healthz  # lumyn-agent
```

#### Detailed Health

```bash
# Check Redis
docker-compose exec redis redis-cli DBSIZE
docker-compose exec redis redis-cli INFO memory

# Check each service's dependencies
docker-compose exec model-gateway curl http://127.0.0.1:8000/healthz
docker-compose exec workflow-engine curl http://redis:6379  # connectivity test
```

### Scaling Services

#### Horizontal Scaling (model-gateway)

```bash
# Scale model-gateway to 3 instances
docker-compose up -d --scale model-gateway=3

# Note: This requires a load balancer (nginx) in front
# For now, manual round-robin or single instance recommended
```

#### Resource Limits

Edit `docker-compose.yml` and add to each service:

```yaml
services:
  model-gateway:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## Troubleshooting

### Redis Issues

#### Symptom: "Redis connection refused"

**Diagnosis:**
```bash
docker-compose ps redis
docker-compose logs redis
```

**Resolution:**
```bash
# Restart Redis
docker-compose restart redis

# Wait for health check
docker-compose exec redis redis-cli ping  # Should print PONG

# Clear data if needed
docker-compose exec redis redis-cli FLUSHALL

# Restart dependent services
docker-compose restart model-gateway workflow-engine
```

#### Symptom: "Redis memory full"

**Diagnosis:**
```bash
docker-compose exec redis redis-cli INFO memory
```

**Resolution:**
```bash
# Set expiration policy
docker-compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Or, increase Redis memory in docker-compose.yml
```

### Model Gateway Issues

#### Symptom: "LLM request timeout"

**Diagnosis:**
```bash
docker-compose logs model-gateway | tail -20
```

**Resolution:**

1. **If using local Ollama:**
   ```bash
   # Check Ollama is running on host
   curl http://host.docker.internal:11434/api/tags
   
   # Or, set cloud-only mode
   export GATEWAY_ROUTING_MODE=cloud-only
   docker-compose restart model-gateway
   ```

2. **If using cloud API:**
   ```bash
   # Verify API keys
   env | grep -E "OPENAI_API_KEY|ANTHROPIC_API_KEY"
   
   # Test API connectivity
   curl -X POST https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```

#### Symptom: "Model not found"

**Diagnosis:**
```bash
curl http://localhost:11430/v1/models
```

**Resolution:**
```bash
# Pull model to local Ollama (if using local-first)
ollama pull llama3.2:3b

# Or, update GATEWAY_MODEL env var
export GATEWAY_MODEL=gpt-4
docker-compose restart model-gateway
```

### Workflow Engine Issues

#### Symptom: "Task stuck in pending state"

**Diagnosis:**
```bash
# Check approval queue
docker-compose exec redis redis-cli LRANGE approvals:pending 0 -1

# Check task state in logs
docker-compose logs workflow-engine | grep "task_123"
```

**Resolution:**
```bash
# Force approval (if safe)
curl -X POST http://localhost:11431/task/task_123/approve \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "notes": "manual override"}'

# Or, reject and retry
curl -X POST http://localhost:11431/task/task_123/approve \
  -H "Content-Type: application/json" \
  -d '{"decision": "reject"}'
```

#### Symptom: "Approval timeout reached"

**Diagnosis:**
```bash
docker-compose logs workflow-engine | grep "APPROVAL_TIMEOUT"
```

**Resolution:**
```bash
# Increase timeout in .env
export APPROVAL_TIMEOUT_SECONDS=600
docker-compose restart workflow-engine

# Or, explicitly approve pending task
curl -X POST http://localhost:11431/task/task_123/approve \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve"}'
```

### Screen Agent Issues

#### Symptom: "DISPLAY not set"

**Diagnosis:**
```bash
docker-compose exec screen-agent printenv | grep DISPLAY
docker-compose logs screen-agent | tail -5
```

**Resolution (Linux):**
```bash
# Start Xvfb (virtual X server)
Xvfb :1 -screen 0 1920x1080x24 &

# Export DISPLAY and restart
export DISPLAY=:1
docker-compose restart screen-agent

# Verify
docker-compose exec screen-agent xdpyinfo | head -5
```

**Resolution (Mac/Windows):**
```bash
# Ensure Docker Desktop is running with display forwarding
# Or, skip screen-agent (not required for browser-only tasks)
```

#### Symptom: "Policy denied action"

**Diagnosis:**
```bash
docker-compose logs screen-agent | grep "POLICY_DENIED"
```

**Resolution:**
```bash
# Adjust policy
export ACTION_POLICY=permissive  # or restrictive, deny-destructive
docker-compose restart screen-agent

# Or, check policy file
cat ./automation/screen-agent/config/policy.yaml
```

### Lumyn Agent Issues

#### Symptom: "Session lost after restart"

**Diagnosis:**
```bash
# Sessions are stored in Redis (in-memory only)
docker-compose exec redis redis-cli KEYS "session:*"
```

**Resolution:**
```bash
# To persist sessions across restarts, use PostgreSQL
# For now, sessions are ephemeral (by design)

# To preserve learnings, ensure learnings JSONL is backed up
cat ./agents/lumyn/logs/learnings.jsonl
```

### Network Issues

#### Symptom: "Host network bridge unavailable (playwright-runner)"

**Diagnosis:**
```bash
# Test connectivity from within container
docker-compose exec workflow-engine ping host.docker.internal

# Or, on Linux
docker-compose exec workflow-engine ping 172.17.0.1
```

**Resolution:**
```bash
# For Mac/Windows, ensure Docker Desktop network settings are correct
# For Linux, use --net=host or add to docker-compose.yml

# Disable playwright if unavailable
export PLAYWRIGHT_RUNNER_URL=http://disabled:11432
docker-compose restart workflow-engine
```

---

## Monitoring & Alerting

### Key Metrics to Monitor

1. **Redis Memory:**
   ```bash
   docker-compose exec redis redis-cli INFO memory
   ```
   Alert if > 80% of limit

2. **Service Health:**
   ```bash
   for svc in model-gateway workflow-engine screen-agent lumyn-agent; do
     curl -s http://localhost:8000/healthz || echo "$svc DOWN"
   done
   ```
   Alert if any service returns non-200

3. **Task Queue Depth:**
   ```bash
   docker-compose exec redis redis-cli LLEN tasks:queue
   ```
   Alert if > 100 pending tasks

4. **Approval Queue:**
   ```bash
   docker-compose exec redis redis-cli LLEN approvals:pending
   ```
   Alert if > 10 pending approvals for > 5 minutes

### Log Aggregation (Recommended)

Setup ELK stack or similar for production:

```bash
# Add log driver to docker-compose.yml
services:
  model-gateway:
    logging:
      driver: "awslogs"
      options:
        awslogs-group: "kryos-model-gateway"
        awslogs-region: "us-east-1"
```

---

## Maintenance

### Regular Tasks

#### Daily
- Review logs for errors: `docker-compose logs | grep ERROR`
- Check Redis memory: `docker-compose exec redis redis-cli INFO memory`
- Verify all health checks passing: `curl http://localhost:11430/healthz`

#### Weekly
- Run full test suite: `make test-all`
- Review approval decisions: `docker-compose logs workflow-engine | grep approved`
- Check disk usage: `docker system df`

#### Monthly
- Update dependencies: `make check-updates` (future target)
- Backup Redis data: `docker-compose exec redis redis-cli BGSAVE`
- Review ARCHITECTURE.md for accuracy

### Database Maintenance

#### Backup Redis

```bash
docker-compose exec redis redis-cli BGSAVE
docker cp $(docker-compose ps -q redis):/data/dump.rdb ./redis-backup-$(date +%s).rdb
```

#### Restore Redis

```bash
docker cp ./redis-backup-123456.rdb $(docker-compose ps -q redis):/data/dump.rdb
docker-compose exec redis redis-cli SHUTDOWN
docker-compose up -d redis
```

#### Clear Redis (Caution!)

```bash
docker-compose exec redis redis-cli FLUSHALL
```

This will:
- Clear all sessions
- Clear approval queue
- Clear task queue
- Lose all state

### Dependency Updates

```bash
# Check for Python updates
pip list --outdated

# Update specific package (and rebuild Docker image)
docker-compose up -d --build model-gateway

# For Node.js
npm outdated
npm update

# Rebuild playwright-runner
docker-compose up -d --build playwright-runner
```

---

## Security

### API Key Management

#### Setting API Keys Securely

```bash
# Never commit keys to git
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="claude-..."

# Create .env locally (gitignored)
cat > .env << EOF
OPENAI_API_KEY=$OPENAI_API_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
EOF

# Verify keys are loaded
docker-compose exec model-gateway env | grep API_KEY
```

#### Rotating API Keys

```bash
# 1. Update .env with new key
export OPENAI_API_KEY="sk-new..."

# 2. Restart model-gateway
docker-compose restart model-gateway

# 3. Verify new key works
curl http://localhost:11430/v1/models

# 4. Test model request
curl -X POST http://localhost:11430/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "test"}]}'
```

### Audit Log Review

```bash
# Review all model requests
cat ./ai-core/model-gateway/logs/queries.jsonl | jq '.'

# Review all task executions
cat ./orchestration/workflow-engine/logs/activities.jsonl | jq '.'

# Review all screen actions
cat ./automation/screen-agent/logs/actions.jsonl | jq '.'

# Search for denials
grep "DENIED\|ERROR" ./automation/screen-agent/logs/actions.jsonl
```

### Access Control

#### Restrict to Localhost Only

In `docker-compose.yml`:
```yaml
services:
  model-gateway:
    ports:
      - "127.0.0.1:11430:8000"  # Localhost only
```

#### Add Authentication (Future)

Add OAuth2 middleware or reverse proxy (nginx) with basic auth.

---

## Disaster Recovery

### Complete System Failure

#### Scenario: All services down, Redis data lost

**Recovery Steps:**

1. Verify infrastructure:
   ```bash
   docker ps -a
   docker volume ls
   ```

2. Rebuild Redis container:
   ```bash
   docker-compose up -d redis
   docker-compose logs redis
   ```

3. Rebuild service containers:
   ```bash
   docker-compose up -d --build
   ```

4. Verify health:
   ```bash
   docker-compose ps
   docker-compose exec model-gateway curl http://127.0.0.1:8000/healthz
   ```

5. Restore learnings (if backed up):
   ```bash
   cp ./backup/lumyn-learnings.jsonl ./agents/lumyn/logs/learnings.jsonl
   ```

### Partial Failure: One Service Down

#### For model-gateway:

```bash
docker-compose restart model-gateway
docker-compose logs model-gateway
```

#### For workflow-engine:

```bash
# Check Redis for orphaned tasks
docker-compose exec redis redis-cli LRANGE tasks:queue 0 -1

# Clear queue if stuck
docker-compose exec redis redis-cli DEL tasks:queue

# Restart
docker-compose restart workflow-engine
```

#### For screen-agent:

```bash
docker-compose restart screen-agent
docker-compose logs screen-agent
```

### Data Loss Prevention

#### Enable Redis Persistence

In `docker-compose.yml`:
```yaml
redis:
  command: redis-server --appendonly yes
  volumes:
    - redis-data:/data
```

#### Backup Schedule

```bash
# Daily backup (cron job)
0 2 * * * docker-compose exec redis redis-cli BGSAVE && \
  cp /var/lib/redis/dump.rdb /backup/dump-$(date +\%s).rdb
```

---

## Degraded Modes & Recovery

### Understanding Degraded Modes

When one or more system components fail, Prady OS enters a "degraded mode" where:
- Critical features remain functional (e.g., chat still works even without screen automation)
- Non-critical features gracefully degrade (e.g., browser automation skipped if Playwright unavailable)
- System continues serving with reduced capability
- Logs clearly indicate which components are offline

### Mode: Screen Agent Unavailable

**When This Occurs:**
- `screen-agent` fails to start (e.g., X11 display not available)
- Container crashes repeatedly
- DISPLAY environment variable not set

**Symptoms:**
- Desktop automation requests return HTTP 503
- Browser automation requests fail with "screen-agent unhealthy"
- Chat and task completion still work for non-visual tasks

**Impact:**
- ✅ Conversational AI: Works normally
- ✅ Task orchestration: Works normally
- ✅ Browser automation (Playwright): Works normally (depends on playwright-runner)
- ❌ Desktop screenshots: Unavailable
- ❌ Mouse/keyboard automation: Unavailable
- ❌ GUI element detection: Unavailable

**Recovery:**

1. **On Linux (with X11):**
   ```bash
   # Start virtual display server if needed
   Xvfb :1 -screen 0 1920x1080x24 &
   
   # Set DISPLAY and restart
   export DISPLAY=:1
   make restart
   
   # Verify
   curl http://localhost:11433/healthz  # Should return 200 OK
   ```

2. **On Headless Systems:**
   ```bash
   # Accept that screen-agent will be unavailable
   # All other services continue to work
   # Use browser automation (Playwright) instead of desktop automation
   ```

### Mode: Model Gateway Fallback (Local Ollama → Cloud APIs)

**When This Occurs:**
- Local Ollama unavailable (network unreachable, no models)
- Cloud API key missing or invalid
- Rate limit exceeded on primary provider

**Symptoms:**
- Requests take longer (fallback chains: local → OpenAI → Anthropic)
- API response latency increases
- Cost implications (using paid cloud APIs instead of local)

**Recovery:**

1. **Restore Local Ollama:**
   ```bash
   # Check Ollama status on host
   curl http://host.docker.internal:11434/api/tags
   
   # If down, start Ollama
   # On Mac: brew services start ollama
   # On Linux: systemctl start ollama
   # On Windows: ollama app
   
   # Pull a model if needed
   ollama pull llama3.2:3b
   
   # Restart model-gateway to use local-first routing
   make restart
   ```

2. **Verify Cloud API Keys:**
   ```bash
   # Check env vars
   env | grep -E "OPENAI_API_KEY|ANTHROPIC_API_KEY"
   
   # Test connectivity
   curl -X POST https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```

3. **Switch Routing Mode:**
   ```bash
   # Use local-only mode (requires Ollama)
   export GATEWAY_ROUTING_MODE=local-only
   make restart
   
   # Or, use cloud-only mode (no Ollama needed)
   export GATEWAY_ROUTING_MODE=cloud-only
   make restart
   ```

### Mode: Redis Unavailable (In-Memory Loss)

**When This Occurs:**
- Redis container crashes
- Data volume corrupted
- Out of memory (container killed)

**Symptoms:**
- All services report "Redis connection refused"
- No persistent state between requests
- Active sessions lost immediately
- Pending approvals lost

**Recovery Steps:**

1. **Quick Restart:**
   ```bash
   docker-compose restart redis
   docker-compose exec redis redis-cli PING  # Wait for PONG
   sleep 5
   docker-compose restart workflow-engine lumyn-agent
   ```

2. **If Data Lost (no backup):**
   ```bash
   # Accept data loss and rebuild
   docker-compose down redis
   docker volume rm prady-os_redis-data
   docker-compose up -d redis
   
   # Restart dependent services
   docker-compose restart workflow-engine lumyn-agent
   ```

3. **If Backup Available:**
   ```bash
   # Restore from backup
   docker-compose cp backup/dump-latest.rdb redis:/data/dump.rdb
   docker-compose restart redis
   ```

**Prevention:**
Enable Redis persistence in `docker-compose.yml`:
```yaml
redis:
  command: redis-server --appendonly yes
  volumes:
    - redis-data:/data
```

### Mode: Workflow Engine Stalled (Approval Backlog)

**When This Occurs:**
- Long-running approval workflows
- Approval timeout reached (default 5 minutes)
- Approval queue backed up

**Symptoms:**
- New task requests return HTTP 503 "workflow-engine unavailable"
- Pending approvals stuck in queue
- Logs show "APPROVAL_TIMEOUT_REACHED"

**Recovery:**

1. **Force-Complete Stuck Tasks:**
   ```bash
   # List pending approvals
   docker-compose exec redis redis-cli LRANGE approvals:pending 0 -1
   
   # Approve a specific task
   curl -X POST http://localhost:11431/task/TASK_ID/approve \
     -H "Content-Type: application/json" \
     -d '{"decision": "approve", "notes": "timeout override"}'
   
   # Or, reject and retry
   curl -X POST http://localhost:11431/task/TASK_ID/approve \
     -H "Content-Type: application/json" \
     -d '{"decision": "reject", "reason": "timeout"}'
   ```

2. **Increase Approval Timeout:**
   ```bash
   # In .env or docker-compose environment
   export APPROVAL_TIMEOUT_SECONDS=900  # 15 minutes
   make restart
   ```

3. **Clear Approval Queue (Data Loss):**
   ```bash
   docker-compose exec redis redis-cli DEL approvals:pending
   docker-compose restart workflow-engine
   ```

### Mode: Memory Pressure (Reduced Capacity)

**When This Occurs:**
- System low on RAM
- Container memory limits exceeded
- Multiple services OOMKilled

**Symptoms:**
- Random service restarts
- Slow responses (swapping)
- Logs show "OOMKilled" or "Memory limit exceeded"

**Recovery:**

1. **Increase Docker Memory Limits:**
   ```bash
   # Update docker-compose.yml
   services:
     model-gateway:
       deploy:
         resources:
           limits:
             memory: 2G  # Increase from 1G
   
   # Reapply
   docker-compose up -d
   ```

2. **Reduce Load (Temporarily):**
   ```bash
   # Stop non-critical services
   docker-compose stop screen-agent lumyn-agent  # Keep model-gateway running
   
   # Or, reduce concurrency
   export GATEWAY_MAX_CONCURRENT_REQUESTS=5  # Default 20
   make restart
   ```

3. **Monitor Memory Usage:**
   ```bash
   docker stats
   docker-compose exec redis redis-cli INFO memory
   ```

### Mode: Network Partition (Service-to-Service Isolation)

**When This Occurs:**
- Docker network misconfigured
- Firewall rules block internal traffic
- DNS resolution fails

**Symptoms:**
- Services report "connection refused" to other services
- Health checks fail for inter-service endpoints
- Logs show "Name resolution failed for 'service-name'"

**Recovery:**

1. **Verify Network Connectivity:**
   ```bash
   # Check if services can reach each other
   docker-compose exec model-gateway nslookup workflow-engine
   docker-compose exec workflow-engine curl http://model-gateway:8000/healthz
   ```

2. **Recreate Network:**
   ```bash
   docker network rm kryos-net
   docker-compose down --remove-orphans
   docker-compose up -d
   ```

3. **Check Service Links:**
   ```bash
   # Verify docker-compose.yml has depends_on constraints
   docker-compose config | grep -A 5 "depends_on"
   ```

### Mode: API Rate Limit Exceeded (Cloud Provider Throttled)

**When This Occurs:**
- Cloud API (OpenAI, Anthropic) rate limit hit
- Too many requests in short time
- Quota exhausted

**Symptoms:**
- Requests return HTTP 429 "Too Many Requests"
- LLM responses delayed or failed
- Model gateway logs show "rate_limit_exceeded"

**Recovery:**

1. **Fallback to Local Ollama:**
   ```bash
   export GATEWAY_ROUTING_MODE=local-only
   make restart
   ```

2. **Implement Request Backoff:**
   ```bash
   # In application code or config
   export GATEWAY_REQUEST_BACKOFF=exponential  # or linear, none
   export GATEWAY_RETRY_MAX_ATTEMPTS=5
   make restart
   ```

3. **Monitor Cloud Usage:**
   ```bash
   # Check OpenAI account usage
   curl https://api.openai.com/dashboard/billing/usage \
     -H "Authorization: Bearer $OPENAI_API_KEY" | jq .
   ```

### Mode: Policy Engine Denies All Actions (Overly Restrictive)

**When This Occurs:**
- Policy mode set to "deny-all" for safety
- Policy file corrupted
- Screen agent in "overly-restrictive" mode

**Symptoms:**
- All desktop automation returns "POLICY_DENIED"
- Logs show "policy_check_failed: action_type=CLICK policy_mode=DENY_ALL"

**Recovery:**

1. **Change Policy Mode:**
   ```bash
   # Switch to permissive mode temporarily
   export ACTION_POLICY=permissive
   make restart
   
   # Then review and fix policy file
   cat ./automation/screen-agent/config/policy.yaml
   ```

2. **Review Policy File:**
   ```bash
   # Ensure policy allows safe actions
   grep -E "allow:|deny:" ./automation/screen-agent/config/policy.yaml
   ```

### Recovery Checklist for Multi-Service Failures

Use this checklist when multiple services are down:

```
[ ] 1. Check docker-compose status: docker-compose ps
[ ] 2. Check Docker daemon: docker ps (should work)
[ ] 3. Restart Redis: docker-compose restart redis
[ ] 4. Wait 5 seconds for health checks to pass
[ ] 5. Restart all services: docker-compose restart
[ ] 6. Verify health endpoints: make health
[ ] 7. Check logs for errors: make logs
[ ] 8. If still failing, do clean rebuild:
      [ ] a. docker-compose down -v
      [ ] b. docker-compose build --no-cache
      [ ] c. docker-compose up -d
      [ ] d. Verify all services healthy
[ ] 9. If still failing, check .env configuration
[ ] 10. If still failing, consult ARCHITECTURE.md for dependency order
```

---

## Support & Escalation

### Getting Help

1. **Review ARCHITECTURE.md** for system design
2. **Check logs** for specific errors
3. **Search troubleshooting guide** above
4. **File a GitHub issue** with logs and environment

### Reporting Issues

Include:
- Docker version: `docker --version`
- Docker Compose version: `docker-compose --version`
- Logs: `docker-compose logs --tail 100`
- Environment: `docker-compose config`
- Reproduction steps

### Performance Issues

Profile using:

```bash
# CPU/Memory per container
docker stats

# Network I/O
docker-compose exec redis redis-cli --bigkeys

# Slow log (Redis)
docker-compose exec redis redis-cli SLOWLOG GET 10
```

---

## Appendix: Common Commands

```bash
# Development
make dev-up              # Start all services
make dev-down            # Stop all services
make logs                # View logs
make test-e2e            # Run E2E tests

# Production
make doctor              # Check environment readiness (when implemented)
make validate            # Run all validations (when implemented)

# Debugging
docker-compose ps                              # List services
docker-compose logs <service>                  # View service logs
docker-compose exec <service> sh               # Interactive shell
docker-compose restart <service>               # Restart service
docker-compose kill <service>                  # Force stop
docker system df                               # Disk usage

# Redis
docker-compose exec redis redis-cli DBSIZE    # Number of keys
docker-compose exec redis redis-cli KEYS "*"  # List all keys
docker-compose exec redis redis-cli FLUSHALL  # Clear all data
docker-compose exec redis redis-cli INFO      # Full statistics

# Health Checks
curl http://localhost:11430/healthz           # model-gateway
curl http://localhost:11431/healthz           # workflow-engine
curl http://localhost:11433/healthz           # screen-agent
curl http://localhost:11436/healthz           # lumyn-agent
```

---

**Document Owner:** Prady OS Team  
**Escalation:** Reach out on GitHub Issues or team Slack  
**Last Updated:** 2025-01-15
