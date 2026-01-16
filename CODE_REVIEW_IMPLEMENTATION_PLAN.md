# Code Review Implementation Plan

Based on [CODE_REVIEW.md](CODE_REVIEW.md) - A staged approach to addressing identified issues.

---

## Phase 1: Before Demo (Quick Fixes) - ~30 minutes

These are low-effort, high-impact fixes that prevent crashes and leaks during demos.

| Issue | File | Effort | Description |
|-------|------|--------|-------------|
| #3 | weather-mcp, ha-mcp | 5 min | Add `timeout=10.0` to all httpx calls |
| #1 | ha-mcp/server.py | 10 min | Redact tokens from logs |
| #4 | main.py | 5 min | Change `logger.error()` to `logger.exception()` |
| #11 | both servers | 5 min | Make debug mode configurable via env var |

**Why first:** These prevent the most embarrassing demo failures - hung requests, leaked credentials in logs, and missing error context.

---

## Phase 2: Reliability (Before Production) - ~2-3 hours

| Issue | File | Effort | Description |
|-------|------|--------|-------------|
| #2 | ha-mcp/server.py | 10 min | Fail fast if HA_TOKEN missing |
| #6 | mcp_client.py, servers | 45 min | Add tenacity retry decorator |
| #7 | ha-mcp/server.py | 15 min | Catch `httpx.RequestError` base class |
| #8 | mcp_client.py | 20 min | Handle JSON parse errors properly |
| #14 | main.py | 30 min | Add graceful shutdown handler |
| #9 | ha-mcp/server.py | 30 min | Verify temperature after setting |

**Why second:** These make the system resilient to transient failures - network blips, API timeouts, and container restarts.

---

## Phase 3: Security - ~2 hours

| Issue | File | Effort | Description |
|-------|------|--------|-------------|
| #10 | web_dashboard.py | 1-2 hrs | Add basic auth or API key middleware |
| #20 | weather-mcp | 10 min | Require LATITUDE/LONGITUDE env vars |

**Why third:** Security matters, but for a home network PoC it's less urgent than stability. Essential before any public exposure.

---

## Phase 4: Quality & Observability - ~4-6 hours

| Issue | File | Effort | Description |
|-------|------|--------|-------------|
| #12 | decision_logger.py | 1 hr | Implement connection pooling |
| #15 | docker-compose.yml | 15 min | Add resource limits |
| #17 | ollama_client.py | 30 min | Extract magic numbers to config |
| #18 | All | 2-3 hrs | Implement structured logging |
| #16 | All | 2+ hrs | Add type hints throughout |

**Why fourth:** These improve maintainability and debugging but don't affect functionality.

---

## Phase 5: Testing - ~4+ hours

| Issue | File | Effort | Description |
|-------|------|--------|-------------|
| #19 | tests/ | 4+ hrs | Add pytest tests for core logic |

**Test priorities:**
1. `BaselineAutomation` decision logic
2. MCP client communication
3. Error scenarios and edge cases
4. Target 70%+ code coverage

---

## Implementation Checklist

### Phase 1
- [ ] #3 - Add HTTP timeouts
- [ ] #1 - Redact tokens from logs
- [ ] #4 - Use logger.exception() for tracebacks
- [ ] #11 - Configurable debug mode

### Phase 2
- [x] #2 - Validate HA_TOKEN at startup
- [x] #6 - Add retry logic with backoff
- [x] #7 - Handle connection errors
- [x] #8 - Handle JSON parse errors
- [x] #14 - Graceful shutdown
- [x] #9 - Verify temperature changes

### Phase 3
- [ ] #10 - Dashboard authentication
- [ ] #20 - Require weather coordinates

### Phase 4
- [ ] #12 - Database connection pooling
- [ ] #15 - Docker resource limits
- [ ] #17 - Extract magic numbers
- [ ] #18 - Structured logging
- [ ] #16 - Type hints

### Phase 5
- [ ] #19 - Unit tests

---

## Notes

- Start with Phase 1 before any demos
- Phase 2 should be complete before running 24/7
- Phase 3 required before exposing outside home network
- Phases 4-5 are ongoing quality improvements
