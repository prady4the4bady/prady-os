# Prady OS v2 Release Guide

**Document Version:** 1.0  
**Last Updated:** 2025  
**Status:** Production Ready  

## Release Overview

This document describes the process for releasing Prady OS v2 from development to production. A release consists of:

1. **Pre-Release Validation:** Verify all systems ready
2. **Release Preparation:** Build and tag artifacts
3. **Release Deployment:** Roll out to production
4. **Post-Release Verification:** Confirm all healthy
5. **Rollback Plan:** Recover if issues arise

---

## Table of Contents

1. [Version Scheme](#version-scheme)
2. [Release Checklist](#release-checklist)
3. [Deployment Pipeline](#deployment-pipeline)
4. [Rollback Procedures](#rollback-procedures)
5. [Release Notes](#release-notes)
6. [Hotfix Process](#hotfix-process)

---

## Version Scheme

Prady OS v2 uses **Semantic Versioning 2.0.0**:

```
MAJOR.MINOR.PATCH

Example: v2.1.3
  2 = Major (breaking changes)
  1 = Minor (new features, backward compatible)
  3 = Patch (bug fixes, no new features)
```

### Version Bumping Rules

- **PATCH:** Bug fixes, security updates (v2.1.3 → v2.1.4)
- **MINOR:** New features, enhanced capabilities (v2.1.4 → v2.2.0)
- **MAJOR:** Breaking API changes, system redesign (v2.0.0 → v3.0.0)

### Release Cadence

- **Regular Releases:** Monthly (first Monday)
- **Security Hotfixes:** As needed (within 24 hours of discovery)
- **Critical Patches:** As needed (production outage)

---

## Release Checklist

### Week 1: Planning

- [ ] Identify features/fixes for release (from GitHub issues)
- [ ] Update VERSION file: `echo "2.X.0" > VERSION`
- [ ] Create release branch: `git checkout -b release/v2.X.0`
- [ ] Update CHANGELOG.md with features
- [ ] Assign release manager
- [ ] Schedule release date

### Week 2-3: Development & Testing

- [ ] All features complete and merged to release branch
- [ ] Code review completed (2+ approvals)
- [ ] Unit tests pass: `make test-all`
- [ ] E2E tests pass: `make test-e2e`
- [ ] Performance benchmarks run (compare to v2.X-1)
- [ ] Security scan passes: `make security-scan` (when implemented)
- [ ] Dependency audit passes: `make audit-deps`

### Release Day: Pre-Deployment

#### Morning (T-4 hours)

- [ ] Final verification on staging: `make validate`
- [ ] Database migration tested (if applicable)
- [ ] Rollback plan reviewed with team
- [ ] Communication prepared (status page, Slack message)
- [ ] On-call rotation confirmed

#### 1 Hour Before

- [ ] Freeze code (no new commits to release branch)
- [ ] Build Docker images: `docker-compose build`
- [ ] Tag images with version: `docker tag model-gateway:latest model-gateway:v2.X.0`
- [ ] Push images to registry: `docker push model-gateway:v2.X.0`
- [ ] Create Git tag: `git tag -a v2.X.0 -m "Release v2.X.0"`
- [ ] Push tag: `git push origin v2.X.0`

#### Deployment

- [ ] Notify stakeholders: "Release v2.X.0 starting at [TIME]"
- [ ] Blue-green deployment: Deploy to alternate infrastructure
- [ ] Health checks: All services passing `/healthz`
- [ ] Smoke tests: Run critical paths (HN task, session persistence)
- [ ] Switch traffic: Update DNS/load balancer to point to new deployment
- [ ] Confirm traffic: Monitor metrics for anomalies

### Post-Deployment (T+30 minutes)

- [ ] All services healthy: `docker-compose ps`
- [ ] No error spikes in logs: `docker-compose logs | grep ERROR`
- [ ] API responses normal: `curl http://localhost:11430/healthz`
- [ ] Database queries fast: `redis-cli --latency`
- [ ] Users reporting normal experience

### Post-Release (T+24 hours)

- [ ] Review logs for errors or warnings
- [ ] Check metrics for anomalies
- [ ] Monitor third-party APIs (OpenAI, Anthropic) for issues
- [ ] Collect user feedback
- [ ] If all clear: Mark release as stable
- [ ] If issues: Proceed to rollback

---

## Deployment Pipeline

### Infrastructure Setup (Pre-Requisite)

```bash
# Build all Docker images with version tag
VERSION=2.X.0
docker-compose build
docker tag $(docker images -q ai-core/model-gateway:latest) ai-core/model-gateway:$VERSION
docker tag $(docker images -q orchestration/workflow-engine:latest) orchestration/workflow-engine:$VERSION
# ... repeat for all services

# Push to registry (or use local registry for private deployment)
docker push ai-core/model-gateway:$VERSION
docker push orchestration/workflow-engine:$VERSION
# ... repeat for all services
```

### Blue-Green Deployment

```bash
# Current state: Green deployment active

# Prepare blue deployment with new version
export BLUE_VERSION=2.X.0
docker-compose -f docker-compose.blue.yml up -d

# Health checks on blue
curl http://localhost:18000/healthz  # model-gateway (blue on 18000)
curl http://localhost:18001/healthz  # workflow-engine (blue on 18001)
# ... all services

# Run smoke tests against blue
make test-e2e ENDPOINT=http://localhost:18000

# Switch traffic from green to blue
# Update DNS/load balancer: 
#   old: 11430 → new: 18000
#   old: 11431 → new: 18001
#   ... all ports

# Keep green running for quick rollback
# Monitor blue for 30 minutes
# Then decommission green
```

### Canary Deployment (Alternative)

```bash
# Route 10% of traffic to new version
# Monitor error rate, latency, throughput
# If OK, increase to 25%, then 50%, then 100%
# If issues, rollback to 0%

# This requires load balancer with canary support
# Not recommended for single-instance deployments
```

### Progressive Rollout

```bash
# Deploy to groups of services in order
# 1. Redis (no dependencies)
# 2. model-gateway (depends: redis)
# 3. workflow-engine (depends: redis, model-gateway)
# 4. screen-agent (depends: model-gateway)
# 5. lumyn-agent (depends: all above)

# Health check after each service
docker-compose restart redis && sleep 15
curl http://localhost:6379  # Redis
curl http://localhost:11430/healthz  # model-gateway
# ... repeat for each service
```

---

## Rollback Procedures

### Quick Rollback (< 5 minutes)

If issues detected immediately after deployment:

```bash
# Step 1: Switch traffic back to previous version
# Update load balancer to use green deployment (if using blue-green)
# OR
docker-compose down  # Stop blue deployment
docker-compose.green.yml up -d  # Start green deployment

# Step 2: Verify old version working
curl http://localhost:11430/healthz

# Step 3: Notify team
# Post to #incidents Slack channel
# "ROLLBACK: v2.X.0 → v2.X-1.0 due to [ISSUE]"
```

### Detailed Rollback

If issues discovered after 30 minutes:

1. **Stop New Deployment:**
   ```bash
   docker-compose kill
   ```

2. **Restore Previous Version:**
   ```bash
   git checkout v2.X-1.0
   docker-compose up -d
   ```

3. **Verify Functionality:**
   ```bash
   docker-compose exec redis redis-cli ping
   curl http://localhost:11430/healthz
   make test-e2e
   ```

4. **Restore Data (if applicable):**
   ```bash
   # Restore Redis snapshot
   docker cp /backup/redis-v2.X-1.0.rdb redis-container:/data/dump.rdb
   docker-compose restart redis
   ```

5. **Confirm Stability:**
   ```bash
   # Monitor logs for 1 hour
   docker-compose logs -f | grep -E "ERROR|CRITICAL"
   ```

### Preventing Cascading Failures

Rollback safeguards:

- [ ] Always keep previous version running (blue-green)
- [ ] Use feature flags to disable new features if issues arise
- [ ] Monitor database migrations (ensure rollback-safe)
- [ ] Test rollback procedure before deployment
- [ ] Maintain 2+ previous versions for quick access

---

## Release Notes

### Release Notes Template

```markdown
# Prady OS v2.X.0

**Release Date:** 2025-XX-XX  
**Previous Version:** v2.X-1.0

## New Features

### Feature 1: [Title]
- [Description]
- [User-visible change]

### Feature 2: [Title]
- [Description]

## Bug Fixes

- [#123] Fixed: [issue description]
- [#124] Fixed: [issue description]

## Security Fixes

- [CVE-XXXX] Fixed: [vulnerability]
- [#125] Fixed: [security issue]

## Improvements

- [#126] Performance: Improved model-gateway latency by 20%
- [#127] UI: Better error messages in lumyn-agent
- [#128] Docs: Updated ARCHITECTURE.md

## Known Issues

- [#129] Browser automation may timeout on slow networks
- [#130] Screen agent requires DISPLAY on Linux

## Dependencies Updated

- Python: 3.11.0 → 3.11.1
- Node.js: 20.0.0 → 20.1.0
- Docker: 4.20 → 4.25
- Redis: 7.0 → 7.2

## Installation / Upgrade

```bash
# Pull latest version
git pull origin main
git checkout v2.X.0

# Install / update
make dev-up
make test-e2e  # Verify
```

## Support

- **Documentation:** https://github.com/kryos/prady-os/blob/main/ARCHITECTURE.md
- **Issues:** https://github.com/kryos/prady-os/issues
- **Security:** security@kryos.dev
```

### Release Notes Checklist

- [ ] Changelog.md updated with all features/fixes
- [ ] Release notes generated from template
- [ ] Release notes reviewed by product team
- [ ] Known issues documented
- [ ] Dependencies listed with versions
- [ ] Installation instructions included
- [ ] Support contacts listed

---

## Hotfix Process

### Urgent Security Issue

**Timeline:** Fix discovered → deployed within 24 hours

1. **Triage (within 1 hour):**
   - Severity assessment (CRITICAL, HIGH, MEDIUM, LOW)
   - Blast radius (how many users affected)
   - Workaround available?

2. **Fix (within 4 hours):**
   ```bash
   git checkout main
   git checkout -b hotfix/security-issue-123
   # Apply fix
   git commit -m "Security: Fix CVE-XXXX"
   ```

3. **Review (within 6 hours):**
   - Expedited review (1 approval minimum)
   - Test affected path
   - No breaking changes

4. **Release (within 24 hours):**
   ```bash
   git tag -a v2.X.1 -m "Hotfix: Security issue"
   docker-compose build
   docker-compose up -d
   make test-e2e
   ```

5. **Communication:**
   - Email all users: "Security update v2.X.1 deployed"
   - Post to security advisory (if critical)
   - Notify security researchers (if CVE)

---

## Deployment Checklist

### Pre-Deployment (1 Week Before)

- [ ] All tests passing on main branch
- [ ] Security scan completed (no HIGH/CRITICAL)
- [ ] Performance benchmarks acceptable
- [ ] Dependency audit completed
- [ ] CHANGELOG.md updated
- [ ] Release notes drafted
- [ ] Stakeholders notified

### Deployment Day

- [ ] Final validation: `make validate`
- [ ] Build and tag images
- [ ] Deploy to staging
- [ ] Run smoke tests
- [ ] Create Git tag and push
- [ ] Deploy to production
- [ ] Monitor for 30 minutes
- [ ] Mark release as stable

### Post-Deployment (24 Hours)

- [ ] Monitor logs for errors
- [ ] Check metrics for anomalies
- [ ] User feedback collection
- [ ] Post-mortem if issues arise
- [ ] Archive release notes

---

## Metrics & Success Criteria

### Release Quality Metrics

```
✓ All unit tests passing: 100%
✓ E2E tests passing: 100%
✓ Code review: 2+ approvals
✓ Security scan: 0 HIGH/CRITICAL issues
✓ Performance: No > 10% regression
✓ Deployment: < 5 minutes downtime
✓ Error rate: < 0.1% post-deployment
✓ User reports: No critical issues in first 24 hours
```

### Deployment Monitoring

```bash
# Error rate (should be stable or improve)
docker-compose logs | grep ERROR | wc -l

# API latency (should be stable or improve)
docker-compose exec redis redis-cli --latency

# Service health (all should be 200)
for svc in 11430 11431 11433 11436; do
  echo "Port $svc:"
  curl -s http://localhost:$svc/healthz || echo "DOWN"
done

# Redis memory (should be stable)
docker-compose exec redis redis-cli INFO memory | grep used_memory_human
```

---

## Appendix: Release Workflow

### Git Workflow

```
main (stable)
  └─ v2.X-1.0 tag
  │
  ├─ feature/X-new-agent (development)
  │
  ├─ bugfix/X-fix-issue (development)
  │
  └─ release/v2.X.0 (release candidate)
       │
       ├─ test: make test-all, make test-e2e
       │
       └─ v2.X.0 tag (when ready)
            │
            └─ Merge back to main (fast-forward)
```

### Release Checklist Automation

```bash
#!/bin/bash
# release-check.sh

echo "Pre-Release Validation"
echo "====================="

# Tests
echo -n "Unit tests: "
make test-unit > /tmp/test-unit.log 2>&1 && echo "✓" || echo "✗"

echo -n "E2E tests: "
make test-e2e > /tmp/test-e2e.log 2>&1 && echo "✓" || echo "✗"

# Security
echo -n "Security scan: "
make security-scan > /tmp/security-scan.log 2>&1 && echo "✓" || echo "✗"

# Validation
echo -n "Configuration validation: "
make validate > /tmp/validate.log 2>&1 && echo "✓" || echo "✗"

# Summary
echo ""
echo "All checks passed! Ready to release."
```

---

**Document Owner:** Release Engineering  
**Last Updated:** 2025-01-15  
**Next Review:** After first production release
