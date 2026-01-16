# MCP IoT PoC - AI Coding Agent Guidelines

This file contains project-specific instructions for AI coding assistants.

## Project Overview

AI-powered thermostat control using Model Context Protocol (MCP). Compares AI decisions vs rule-based automation.

**Stack:**
- **Agent**: Python 3.11, FastAPI, APScheduler, SQLite
- **MCP Servers**: Python 3.11, Starlette, httpx, mcp-sdk
- **LLM**: Ollama (ministral-3:14b recommended) - external dependency
- **Infrastructure**: Docker Compose

## Architecture

```
mcp-iot-poc/
├── agent/src/climate_agent/  → Main app, FastAPI dashboard, port 8080
├── servers/weather-mcp/      → Open-Meteo API wrapper, port 8081
└── servers/homeassistant-mcp/→ HA REST API wrapper, port 8082
```

## Critical Rules 🚨

1. **No SSWS/API Keys**: All auth uses OAuth2 or Bearer tokens
2. **Temperature Bounds**: Always enforce MIN_TEMP/MAX_TEMP (17-23°C default)
3. **MCP Protocol**: Use JSON-RPC 2.0 over HTTP POST to `/mcp`
4. **Tool Validation**: LLMs may pass invalid params - always validate inputs
5. **Async Only**: All HTTP calls must be async with `httpx.AsyncClient`
6. **Retry Logic**: Use `tenacity` for HTTP retries with exponential backoff

## Key Files

| File | Purpose |
|------|---------|
| `agent/src/climate_agent/main.py` | Agent loop, scheduler, baseline comparison |
| `agent/src/climate_agent/mcp_client.py` | MCP protocol client with retries |
| `agent/src/climate_agent/ollama_client.py` | LLM integration |
| `agent/src/climate_agent/decision_logger.py` | SQLite logging + settings storage |
| `agent/src/climate_agent/web_dashboard.py` | FastAPI routes + HTML templates |
| `servers/*/src/*/server.py` | MCP server implementations |

## Development Commands

```bash
# Run locally
docker-compose up -d

# View logs
docker-compose logs -f agent

# Run tests
cd agent && pip install -e ".[dev]" && pytest tests/ -v

# Test MCP servers
curl http://localhost:8081/health  # weather-mcp
curl http://localhost:8082/health  # homeassistant-mcp
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HA_URL` | Yes | Home Assistant URL |
| `HA_TOKEN` | Yes | HA long-lived access token |
| `OLLAMA_URL` | Yes | Ollama API endpoint |
| `LATITUDE` | Yes | Location latitude (weather) |
| `LONGITUDE` | Yes | Location longitude (weather) |
| `DASHBOARD_USER` | No | Dashboard basic auth username |
| `DASHBOARD_PASS` | No | Dashboard basic auth password |
| `LOG_FORMAT` | No | `text` (default) or `json` |

## Common Patterns

### Adding a new MCP tool
```python
# In server.py list_tools():
Tool(name="tool_name", description="...", inputSchema={...})

# In call_tool():
elif name == "tool_name":
    # validate and execute
```

### Adding a dashboard setting
```python
value = await self.logger.get_setting("key", "default", "Description", "Category")
```

## Code Review Status

All phases complete! See `CODE_REVIEW.md` for details.

| Phase | Status |
|-------|--------|
| Phase 1 (Demo fixes) | ✅ Complete |
| Phase 2 (Reliability) | ✅ Complete |
| Phase 3 (Security) | ✅ Complete |
| Phase 4 (Quality) | ✅ Complete |
| Phase 5 (Testing) | ✅ Complete |

## Testing

Tests are in `agent/tests/` using pytest:
- `test_baseline_automation.py` - Decision logic
- `test_mcp_client.py` - MCP communication
- `test_ollama_client.py` - LLM integration
- `test_decision_logger.py` - Database operations

CI runs tests automatically on push via GitHub Actions.
