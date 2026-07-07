# Section 8: Stress-Test Plan (Before Production Launch)

## Executive Summary
Before launching SaaS, Phantom must survive brutal real-world scenarios: 10K concurrent users, region failures, database crashes, network latency spikes. This section defines the test matrix + playbook.

---

## Test Objective
**Prove:** Phantom can handle 10x the expected load (conservative estimate: 1K → 10K concurrent sessions) with:
- **Latency (p99):** < 200ms
- **Error rate:** < 0.1%
- **Zero data loss:** Every auth receipt cryptographically signed + recoverable.
- **Graceful degradation:** At max load, prioritize in-flight sessions (new sessions queued, not dropped).

---

## Test Environment Setup

### Infrastructure
```
┌─ Load Generator ─────────────────────────────┐
│  k6 / JMeter (controller)                    │
│  - Generates 10K concurrent users            │
│  - Stages: ramp-up (1→10K in 10min),        │
│           steady (10K for 30min),            │
│           ramp-down (10K→0 in 10min)        │
└────────────────────────────────────────────┘
        ↓
┌─ Phantom SaaS (Staging) ─────────────────┐
│  Load Balancer (AWS ALB)                   │
│    ↓          ↓          ↓                 │
│  Pod-1     Pod-2     Pod-3                 │
│  (US East, EU West, AP Southeast)          │
└────────────────────────────────────────────┘
        ↓                    ↓
┌─ PostgreSQL ──────────────────┐  Monitoring (Prometheus)
│  Primary (us-east-1)           │  - Request latency
│  Replicas x2                   │  - Error rate
│  (multi-region)                │  - Database connection pool
└────────────────────────────────┘  - CPU / Memory / Disk I/O
```

### Baseline Metrics (Before Load Test)
Run the following baseline first (no load):
```bash
# Single request latency
$ curl -s -o /dev/null -w "%{time_total}\n" https://staging.phantom.internal/api/v1/health
# Expected: <50ms

# Database query time (cold)
$ psql -h phantom-db.staging.aws.amazon.com -d phantom_test -c "SELECT COUNT(*) FROM sessions;"
# Expected: <10ms

# Cache hit rate (if using Redis)
$ redis-cli info stats | grep hits
# Expected: >90% hit rate
```

---

## Test Scenario 1: Ramp-Up (Gradual Load Increase)

### Objective
Prove system scales linearly from 1K → 10K concurrent users without cascading failure.

### Load Profile (k6 Script)
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = 'https://staging-phantom.example.com';

export const options = {
  stages: [
    { duration: '10m', target: 10000 }, // Ramp up from 0 to 10K
    { duration: '30m', target: 10000 }, // Stay at 10K
    { duration: '10m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<200'],   // 99th percentile < 200ms
    http_req_failed: ['rate<0.001'],    // Error rate < 0.1%
  },
};

export default function () {
  const userId = __VU; // Virtual user ID (1-10000)
  const sessionId = Math.random().toString(36).substr(2, 9);

  // Initiate authentication
  let response = http.post(`${BASE_URL}/api/v1/users/${userId}/authenticate`, {
    device_id: `device-${userId}`,
    session_id: sessionId,
  }, {
    headers: { 'X-API-Key': 'test-key-12345' },
  });

  check(response, {
    'POST /authenticate returned 200': (r) => r.status === 200,
    'Response time < 200ms': (r) => r.timings.duration < 200,
  });

  // Poll session status (simulate real client behavior)
  sleep(1); // Wait 1 second
  response = http.get(`${BASE_URL}/api/v1/sessions/${sessionId}/status`, {
    headers: { 'X-API-Key': 'test-key-12345' },
  });

  check(response, {
    'GET /status returned 200': (r) => r.status === 200,
    'Session verified within 5s': (r) => r.json().status === 'verified' || r.json().status === 'pending',
  });

  sleep(1);
}
```

### Expected Results
| Metric | Target | Pass/Fail |
|--------|--------|-----------|
| p99 latency | <200ms | ✓ |
| p95 latency | <100ms | ✓ |
| Error rate | <0.1% | ✓ |
| Max DB connections | <800/1000 | ✓ |
| Pod CPU | <80% | ✓ |
| Pod Memory | <85% | ✓ |

### Failure Scenarios & Recovery

| Scenario | Expected Behavior | Pass/Fail |
|----------|-------------------|-----------|
| **At 2K concurrent (ramp phase):** Latency spikes to 300ms | Acceptable (recovery within 30s) | ✓ |
| **At 5K concurrent:** Database connections reach 400/1000 | Acceptable (scaling linear, no deadlock) | ✓ |
| **At 10K concurrent (peak):** Pod CPU reaches 75% | Acceptable (HPA scales to Pod-4) | ✓ |
| **Pod-3 OOM killed:** Traffic rerouted to Pod-1, Pod-2 | Recovery <5s, no errors | ✓ |

### Troubleshooting Checklist
- ❌ Latency jumps to 1000ms+ → Database query timeout. Check slow query log.
- ❌ Error rate spikes to 5%+ → Connection pool exhaustion. Increase to 2000.
- ❌ Pod crashes → Memory leak in LangGraph orchestration. Profile heap.
- ❌ Database deadlock → Concurrent transactions on same rows. Add row-level locking audit.

---

## Test Scenario 2: Steady State (Sustained Load)

### Objective
Prove system is stable under peak load for 30 minutes (no memory leaks, connection pools don't drift).

### Load Profile
- 10K concurrent sessions maintained for 30 minutes.
- Every 5 minutes: 1K new users arrive, 1K old users leave (session churn).
- Background job: Analytics aggregation (read-heavy).

### Key Metrics to Monitor
```
Every 1 minute:
  - avg latency (should be stable ±10%)
  - p99 latency (should be stable ±10%)
  - error rate (should stay <0.1%)
  - database connections (should not grow)
  - memory usage per pod (should not grow)
  - response time distribution (check for bimodal)

Every 5 minutes:
  - database size (should not grow due to bloat)
  - index fragmentation (should not degrade)
  - session cache hit rate (should stay >90%)
```

### Expected Results
| Metric | Time | Value | Pass/Fail |
|--------|------|-------|-----------|
| Avg latency | Minute 1 | 80ms | ✓ |
| Avg latency | Minute 30 | 82ms | ✓ (stable) |
| p99 latency | Minute 1 | 150ms | ✓ |
| p99 latency | Minute 30 | 155ms | ✓ (stable) |
| Pod memory | Minute 1 | 2GB | ✓ |
| Pod memory | Minute 30 | 2.1GB | ✓ (no leak) |
| DB connections | Minute 1 | 750/1000 | ✓ |
| DB connections | Minute 30 | 755/1000 | ✓ (stable) |

### Failure Scenarios

| Scenario | Expected | Pass/Fail |
|----------|----------|-----------|
| **Latency drifts from 80ms → 200ms+ over 30min** | Memory leak suspected. Check GC logs. | ❌ FAIL |
| **P99 latency spikes every 5min (correlated with new users)** | Cold cache hits / GC pause. Acceptable if <200ms. | ⚠️ OK |
| **Database connections climb from 750 → 900 over 30min** | Connection leak. Check for unclosed connections. | ❌ FAIL |
| **Error rate gradually increases (1% → 5%)** | Resource exhaustion or cascading timeout. | ❌ FAIL |

---

## Test Scenario 3: Region Failure (Chaos Engineering)

### Objective
Prove multi-region failover works without user-visible impact.

### Test Setup
- Load test with 5K concurrent users spread across 3 regions.
- Monitor traffic distribution: 1667/region (roughly equal).

### Failure Injection (30min into steady state)
```bash
# Option 1: Kill a pod
kubectl delete pod phantom-prod-pod-2 -n phantom-prod

# Option 2: Inject network latency
# (Simulate network partition on Pod-2)
tc qdisc add dev eth0 root netem delay 2000ms  # 2 second delay

# Option 3: Simulate database connection failure
# (Block TCP port 5432 on EU-West replica)
iptables -I INPUT -p tcp --dport 5432 -j DROP
```

### Expected Recovery
| Metric | Before Failure | During (5s) | After Recovery (30s) | Pass/Fail |
|--------|---|---|---|---|
| Error rate | 0.1% | 2–5% (spike) | <0.2% | ✓ |
| P99 latency | 150ms | 400ms (spike) | 160ms | ✓ |
| Traffic to Pod-2 | 1667 req/s | 0 req/s | 0 req/s (rerouted) | ✓ |
| Session loss | 0 | <5 sessions | 0 (recovered) | ✓ |

### Acceptance Criteria
- ✓ Users see <2 second of degradation (acceptable).
- ✓ No session data loss (all inflight sessions signed + recoverable).
- ✓ Traffic automatically reroutes within 5 seconds.
- ✓ No manual intervention required.

---

## Test Scenario 4: Database Failure (Recovery)

### Objective
Prove database failure recovery works without data loss.

### Test Setup
- 2K concurrent sessions (lower load, focus on correctness).
- Primary database + 2 read replicas (multi-region).

### Failure Injection (15min into test)
```bash
# Option 1: Stop primary database
aws rds stop-db-instance --db-instance-identifier phantom-prod-primary

# Option 2: Simulate connection pool exhaustion
# (Block all incoming TCP to primary DB)
iptables -I INPUT -p tcp --dport 5432 -s 10.0.0.0/8 -j DROP
```

### Expected Failover
| Event | Expected Behavior | Timeout |
|-------|-------------------|---------|
| **DB outage detected** | Health check fails 2x (10s) | 10s |
| **Failover triggered** | Promote replica to primary | 30s |
| **DNS updated** | Route traffic to new primary | 5s |
| **Application reconnects** | All pods reconnect to new primary | 10s |
| **Sessions continue** | New auth requests resume | 60s (acceptable) |

### Acceptance Criteria
- ✓ RTO (Recovery Time Objective): <2 minutes.
- ✓ RPO (Recovery Point Objective): <1 minute of data loss.
- ✓ No corruption in recovered database.
- ✓ Audit trail is intact (all receipts recoverable).

### Verification Query (Post-Failover)
```sql
-- Check data integrity
SELECT COUNT(*) FROM sessions WHERE status = 'verified';
SELECT COUNT(*) FROM receipts WHERE signature_valid = true;
SELECT COUNT(*) FROM audit_log WHERE timestamp > now() - interval '2 hours';
-- Expected: Continuous growth, no drops.
```

---

## Test Scenario 5: High Latency Network (Slowdown Injection)

### Objective
Prove system degrades gracefully under network latency (400ms+ latency simulating intercontinental).

### Test Setup
- 2K concurrent users.
- Inject 400ms latency between load generator and Phantom.

### Load Profile (k6 Script with Latency)
```javascript
export const options = {
  stages: [
    { duration: '5m', target: 2000 },
    { duration: '10m', target: 2000 }, // Sustained under high latency
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(99)<1000'], // Relaxed threshold (400ms network + 200ms service = 600ms)
  },
};

export default function () {
  // Same as Scenario 1, but network adds 400ms
  // Total p99 expected: ~600ms (400ms network + 200ms service)
}
```

### Expected Results
| Metric | Target | Pass/Fail |
|--------|--------|-----------|
| p99 total latency | <1000ms | ✓ |
| p99 server-side latency | <200ms | ✓ |
| Error rate | <0.1% | ✓ |
| Session success rate | >99% | ✓ |

### Graceful Degradation Checks
- ✓ Client-side retries work (if response times out).
- ✓ Sessions don't hang (implement 30s timeout).
- ✓ Users aren't rate-limited due to slow responses (track by session, not request).

---

## Test Scenario 6: Peak Load Edge Case (10K + Burst)

### Objective
Prove system can handle temporary traffic spike (1.5x peak = 15K concurrent).

### Test Setup
- Ramp to 10K concurrent over 5 minutes.
- At minute 15, spike to 15K for 2 minutes (simulate peak event).
- Return to 10K for 5 minutes.
- Ramp down to 0.

### Expected Results
| Phase | Concurrent | Latency | Error Rate | Queue Depth | Pass/Fail |
|-------|---|---|---|---|---|
| Ramp to 10K | 0→10K | <200ms | <0.1% | — | ✓ |
| Steady 10K | 10K | <200ms | <0.1% | <100 queued | ✓ |
| Spike to 15K | 10K→15K | <300ms (acceptable) | <1% (acceptable) | <1K queued | ⚠️ OK |
| Return to 10K | 15K→10K | <200ms | <0.1% | <100 queued | ✓ |

### Acceptance Criteria
- ✓ No crash, no deadlock during spike.
- ✓ Graceful degradation: New requests queued, not dropped.
- ✓ Error rate stays <1% (higher than normal, but acceptable).
- ✓ System returns to normal within 5 minutes of spike.

### Fallback Behavior (if overloaded)
```
If queue depth > 5000:
  - Return 503 (Service Unavailable) to new requests.
  - Include `Retry-After: 30` header.
  - Clients should back off + retry later.
  - (Prevents thundering herd on recovery.)
```

---

## Test Execution Roadmap

| Phase | Test Scenario | Timeline | Owner | Success Metric |
|-------|---|---|---|---|
| **Week 1** | Scenario 1 (Ramp-up) | 3 days | QA + SRE | All thresholds met |
| **Week 2** | Scenario 2 (Steady state) | 2 days | QA + SRE | Memory stable, latency stable |
| **Week 2** | Scenario 3 (Region failure) | 2 days | SRE | Failover <5s, no data loss |
| **Week 3** | Scenario 4 (DB failure) | 2 days | SRE + DBA | RTO <2min, RPO <1min |
| **Week 3** | Scenario 5 (High latency) | 1 day | QA | p99 <1000ms, <0.1% error |
| **Week 3** | Scenario 6 (Peak burst) | 1 day | QA | No crash, graceful queue |

**Total timeline:** 2 weeks.  
**Team:** 1 QA engineer, 2 SRE engineers.  
**Cost:** ~$20K (engineer time + infrastructure).

---

## Pass/Fail Criteria

### PASS (Ready for Production)
✓ All 6 scenarios pass thresholds (see tables above).  
✓ Zero data loss across all scenarios.  
✓ Zero unplanned restarts / crashes.  
✓ RTO < 2 minutes (database failure recovery).  
✓ Failover <5 seconds (region failure).  
✓ Memory leak rate < 1MB/hour (steady state).

### FAIL (Back to Engineering)
❌ Any scenario fails a threshold.  
❌ Data loss detected (even 1 receipt).  
❌ Unplanned pod crash / OOM kill.  
❌ Database deadlock or corruption.  
❌ Failover >5 seconds.  
❌ Memory leak >10MB/hour.

---

## Post-Test Artifacts

### Must Collect
- Load test report: latency distribution, error trace, timelines (HTML from k6).
- Prometheus metrics: 2-week time series (CPU, memory, connections).
- PostgreSQL slow query log: Queries >500ms (check for missing indexes).
- Application logs: All errors + warnings during test.
- Flame graphs: CPU profiling (identify bottlenecks).

### Analysis Checklist
- [ ] Latency distribution is unimodal (not bimodal / multimodal = suspect issue).
- [ ] Error trace shows no pattern (all errors random, not correlated).
- [ ] Database query times are stable (not degrading over time).
- [ ] Network throughput is stable (no packet loss / retransmits).
- [ ] Memory usage is stable (no leak suspected).

### Runbook Deliverable
Create a "Stress Test Failure Playbook" documenting:
- Common failure modes (e.g., "latency spikes to 1000ms").
- Root cause diagnosis (e.g., "check slow query log").
- Recovery steps (e.g., "add index on sessions.user_id").

---

## Critical Success Factor

**You MUST run these tests before launching SaaS.** If you skip this:
- Customers will experience outages (you'll lose trust).
- Competitors will have better uptime (you'll lose deals).
- Regulators will fine you for SLA breach (you'll lose revenue).

**Run these tests. Pass them. Then launch.**
