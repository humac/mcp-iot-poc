# MCP IoT PoC - AI Coding Agent Guidelines

This file contains project-specific instructions for AI coding assistants.

## Project Overview

AI-powered thermostat control using Model Context Protocol (MCP). Compares AI decisions vs rule-based automation.

**Stack:**
- **Agent**: Python 3.11, FastAPI, APScheduler, SQLite
- **MCP Servers**: Python 3.11, Starlette, httpx, mcp-sdk
- **LLM**: Ollama (llama3.1:8b) - external dependency
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
6. **No Tests Yet**: Phase 5 will add tests - for now, test via Docker

## Key Files

| File | Purpose |
|------|---------|
| `agent/src/climate_agent/main.py` | Agent loop, scheduler, baseline comparison |
| `agent/src/climate_agent/mcp_client.py` | MCP protocol client |
| `agent/src/climate_agent/ollama_client.py` | LLM integration |
| `agent/src/climate_agent/decision_logger.py` | SQLite logging + settings storage |
| `agent/src/climate_agent/web_dashboard.py` | FastAPI routes + Jinja2 templates |
| `servers/*/src/*/server.py` | MCP server implementations (Starlette) |
| `docker-compose.yml` | Container orchestration |

## Development Commands

```bash
# Run locally
docker-compose up -d

# View logs
docker-compose logs -f agent

# Test MCP servers
curl http://localhost:8081/health  # weather-mcp
curl http://localhost:8082/health  # homeassistant-mcp

# Call MCP tool
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## Common Patterns

### Adding a new MCP tool
1. Add `Tool()` to `list_tools()` in `server.py`
2. Handle in `call_tool()` switch statement
3. Include input validation for LLM quirks (they send wrong types!)

### Adding a new dashboard setting
Use `DecisionLogger.get_setting()` - auto-creates missing settings:
```python
value = await self.logger.get_setting(
    "key", 
    "default", 
    "Description for UI", 
    "Category"
)
```

### Making HTTP requests
Always use async client with timeout:
```python
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(url, headers=headers)
    response.raise_for_status()
```

## Code Review Status

Tracked in `CODE_REVIEW.md` and `CODE_REVIEW_IMPLEMENTATION_PLAN.md`:

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Demo fixes (timeouts, logging) |
| Phase 2 | 🔄 In Progress | Reliability (retries, shutdown) |
| Phase 3 | ⏳ Pending | Security (auth, validation) |
| Phase 4 | ⏳ Pending | Quality (pooling, types) |
| Phase 5 | ⏳ Pending | Testing (pytest, coverage) |

## Agent Helper Files

This project includes agent-specific instruction files:
- `GEMINI.md` - Google Gemini / Jules
- `CLAUDE.md` - Anthropic Claude
- `.cursorrules` - Cursor IDE
- `.github/copilot-instructions.md` - GitHub Copilot
- `.windsurfrules` - Windsurf (Codeium)
