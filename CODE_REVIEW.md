# Code Review: MCP IoT PoC

**Date:** 2026-01-14
**Reviewer:** Claude Code
**Status:** Pending Implementation

---

## Executive Summary

This is a well-structured prototype demonstrating MCP with local LLM inference. The architecture is clean with good separation of concerns, but there are security and reliability issues that need attention before production use.

---

## Critical Issues

### 1. Credential Exposure in Logs
**File:** `servers/homeassistant-mcp/src/ha_mcp/server.py:264`
**Status:** [x] Fixed

MCP requests containing auth tokens are logged:
```python
logger.info(f"MCP request: {body}")  # Could contain sensitive data
```

**Fix:** Sanitize sensitive data before logging. Create a helper function to redact tokens.

---

### 2. Missing HA_TOKEN Validation at Startup
**File:** `servers/homeassistant-mcp/src/ha_mcp/server.py:29-30`
**Status:** [x] Fixed

Missing token only produces a warning, container starts anyway:
```python
if not HA_TOKEN:
    logger.warning("HA_TOKEN not set - API calls will fail")  # Should raise!
```

**Fix:** Raise exception at startup if critical env vars are missing:
```python
if not HA_TOKEN:
    raise ValueError("HA_TOKEN environment variable is required")
```

---

### 3. No Timeout on External HTTP Calls
**Files:**
- `servers/weather-mcp/src/weather_mcp/server.py:62`
- `servers/homeassistant-mcp/src/ha_mcp/server.py:51`

**Status:** [x] Fixed

HTTP requests can hang indefinitely:
```python
response = await client.get(OPEN_METEO_URL, params=params)  # No timeout!
```

**Fix:** Add `timeout=10.0` to all httpx calls:
```python
async with httpx.AsyncClient(timeout=10.0) as client:
```

---

### 4. Unhandled Exception Swallowing
**File:** `agent/src/climate_agent/main.py:299-305`
**Status:** [x] Fixed

Generic exception catch loses traceback:
```python
except Exception as e:
    logger.error(f"Evaluation error: {e}")  # No traceback!
```

**Fix:** Use `logger.exception()` to include full traceback:
```python
except Exception as e:
    logger.exception("Evaluation error")
```

---

## High Priority Issues

### 5. Race Condition in Tool Result Extraction
**File:** `agent/src/climate_agent/main.py:238-245`
**Status:** [ ] Not Fixed

If tools are called multiple times, only the LAST result is retained.

**Fix:** Validate all required data was gathered before proceeding.

---

### 6. Missing Retry Logic for Transient Failures
**Files:** Multiple
**Status:** [x] Fixed

No retry logic for network errors or transient API failures.

**Fix:** Add exponential backoff retry decorator:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def fetch_with_retry(...):
```

---

### 7. Incomplete HTTP Error Handling
**File:** `servers/homeassistant-mcp/src/ha_mcp/server.py:228-233`
**Status:** [x] Fixed

Only catches `HTTPStatusError`, not connection errors.

**Fix:** Catch `httpx.RequestError` base class:
```python
except httpx.RequestError as e:
    logger.error(f"Connection error: {e}")
except httpx.HTTPStatusError as e:
    logger.error(f"HTTP error: {e.response.status_code}")
```

---

### 8. JSON Parsing Errors Silently Ignored
**File:** `agent/src/climate_agent/mcp_client.py:79-83`
**Status:** [x] Fixed

JSONDecodeError silently falls back to text, causing downstream issues.

**Fix:** Raise exception or return clear error structure.

---

### 9. No Verification After Setting Temperature
**File:** `servers/homeassistant-mcp/src/ha_mcp/server.py:155-173`
**Status:** [x] Fixed

Temperature is set but no confirmation that HA actually applied the change.

**Fix:** Read back thermostat state after setting to verify.

---

## Medium Priority Issues

### 10. Unprotected Web Dashboard
**File:** `agent/src/climate_agent/web_dashboard.py`
**Status:** [x] Fixed

Dashboard is completely unprotected - anyone on network can see thermostat data.

**Fix:** Add basic authentication:
```python
from starlette.authentication import requires
from starlette.middleware.authentication import AuthenticationMiddleware
```

---

### 11. Debug Mode Enabled in Production
**Files:**
- `servers/homeassistant-mcp/src/ha_mcp/server.py:322`
- `servers/weather-mcp/src/weather_mcp/server.py:263`

**Status:** [x] Fixed

```python
app = Starlette(debug=True, ...)  # Should be False in production
```

**Fix:**
```python
app = Starlette(debug=os.getenv("DEBUG", "false").lower() == "true", ...)
```

---

### 12. New DB Connection Per Call
**File:** `agent/src/climate_agent/decision_logger.py`
**Status:** [ ] Not Fixed

Creates new SQLite connection for every database operation.

**Fix:** Implement connection pooling or persistent connection.

---

### 13. Hardcoded Baseline Rules
**File:** `agent/src/climate_agent/main.py:36-116`
**Status:** [ ] Not Fixed

Baseline automation rules are hardcoded in Python.

**Fix:** Move to configuration file (YAML/JSON) for easy customization.

---

### 14. No Graceful Shutdown
**File:** `agent/src/climate_agent/main.py:357-359`
**Status:** [x] Fixed

Doesn't wait for in-flight requests or scheduled jobs to complete.

**Fix:** Implement graceful shutdown with timeout:
```python
@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=True)
    # Wait for in-flight operations
```

---

### 15. No Resource Limits in Docker
**File:** `docker-compose.yml`
**Status:** [x] Fixed

No CPU or memory limits specified.

**Fix:** Add resource limits:
```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1024M
    reservations:
      cpus: '0.5'
      memory: 512M
```

---

## Low Priority Issues

### 16. Missing Type Hints
**Files:** Multiple
**Status:** [ ] Not Fixed

Many functions lack complete type hints.

**Fix:** Add complete type hints, use `Callable`, `Awaitable` for function types.

---

### 17. Magic Numbers and Hardcoded Constants
**File:** `agent/src/climate_agent/ollama_client.py:65`
**Status:** [x] Fixed

```python
timeout=120.0,  # Why 120? Not configurable
```

**Fix:** Extract to named constants or environment variables.

---

### 18. No Structured Logging
**Files:** All
**Status:** [ ] Not Fixed

Logs use string formatting which is hard to parse/query.

**Fix:** Use structured logging (JSON format) with `structlog` or `python-json-logger`.

---

### 19. No Unit Tests
**Status:** [ ] Not Fixed

No test files present in the project.

**Fix:** Add unit tests for:
- `BaselineAutomation` logic
- MCP client communication
- Error scenarios and edge cases
- Target 70%+ code coverage

---

### 20. Hardcoded Coordinates Default Silently
**File:** `servers/weather-mcp/src/weather_mcp/server.py:28-29`
**Status:** [x] Fixed

Default coordinates are hardcoded; if not configured, silently uses defaults.

**Fix:** Require env vars or raise error with helpful message.

---

## Strengths (No Action Needed)

- Clean architecture with separation of concerns
- Good async/await patterns
- Correct MCP implementation
- Thoughtful baseline comparison feature
- Well-structured Docker deployment

---

## Implementation Priority

### Phase 1: Before Demo (Immediate)
- [x] Add timeouts to HTTP calls (#3)
- [x] Remove token logging (#1)
- [x] Use `logger.exception()` for error tracebacks (#4)
- [x] Disable debug mode (#11)

### Phase 2: Before Production
- [ ] Add dashboard authentication (#10)
- [ ] Config validation at startup (#2)
- [ ] Retry logic with backoff (#6)
- [ ] Graceful shutdown (#14)

### Phase 3: Quality Improvements
- [x] Connection pooling (#12) - Partial
- [x] Resource limits (#15)
- [x] Unit tests (#19)
- [ ] Structured logging (#18)
- [ ] Type hints (#16)

---

## Notes

- This review was conducted on 2026-01-14
- Project is a PoC/demo, not production-ready
- Focus on critical fixes before any live demo
- Consider security hardening before sharing publicly
