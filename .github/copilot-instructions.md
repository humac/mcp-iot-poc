# MCP IoT PoC - GitHub Copilot Guidelines

## Project Overview
AI-powered thermostat control using Model Context Protocol (MCP). Compares AI decisions vs rule-based automation.

**Stack:**
- **Agent**: Python 3.11, FastAPI, APScheduler, SQLite
- **MCP Servers**: Python 3.11, Starlette, httpx, mcp-sdk
- **LLM**: Ollama (ministral-3:14b recommended)
- **Infrastructure**: Docker Compose

## Critical Rules 🚨

1. **No SSWS/API Keys**: All auth uses OAuth2 or Bearer tokens
2. **Temperature Bounds**: Always enforce MIN_TEMP/MAX_TEMP (17-23°C default)
3. **MCP Protocol**: Use JSON-RPC 2.0 over HTTP POST to `/mcp`
4. **Tool Validation**: LLMs may pass invalid params - always validate inputs
5. **Async Only**: All HTTP calls must be async with `httpx.AsyncClient`
6. **Retry Logic**: Use `tenacity` for HTTP retries with exponential backoff

## Development

```bash
# Run locally
docker-compose up -d

# Run tests
cd agent && pip install -e ".[dev]" && pytest tests/ -v

# View logs
docker-compose logs -f agent
```

## Code Review Status
All phases complete - see `CODE_REVIEW.md` for details.

## Testing
Tests in `agent/tests/` using pytest. CI runs automatically via GitHub Actions.
