# MCP IoT POC: AI-Powered Thermostat Control

An autonomous AI agent that uses weather forecasts to make intelligent thermostat decisions. Built using the **Model Context Protocol (MCP)** to demonstrate agentic AI with IoT integration.

This project compares AI-driven decision making against traditional rule-based Home Assistant automations, showing when and why an AI agent makes different (often better) choices.

## 🎯 Project Goals

1. **Learn MCP** - Understand the Model Context Protocol by building real MCP servers
2. **Demonstrate AI vs Automation** - Show the difference between rule-based and reasoning-based control
3. **Build a Practical Demo** - Create something that actually runs and makes real decisions

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Docker Environment                                                 │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ LLM Provider│  │ Weather MCP │  │ Ecobee MCP  │  │ Agent      │  │
│  │ (Ollama/    │◄─┤ Server      │◄─┤ Server      │◄─┤ Loop       │  │
│  │ OpenAI/etc) │  │ :8081       │  │ :8082       │  │ :8080      │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │
│                          │                 │                        │
└──────────────────────────┼─────────────────┼────────────────────────┘
                           │                 │
                    Open-Meteo API       Ecobee API
                      (Internet)         (Internet)
```

### Components

| Component | Port | Description |
|-----------|------|-------------|
| `weather-mcp` | 8081 | MCP server wrapping Open-Meteo weather API |
| `ecobee-mcp` | 8082 | MCP server for direct Ecobee thermostat control |
| `agent` | 8080 | Autonomous agent with web dashboard |
| LLM Provider | varies | Ollama (local), OpenAI, Anthropic, or Google Gemini |

## 🔑 Key Features

### AI vs Baseline Comparison

Every evaluation cycle, the agent:
1. Gathers weather and thermostat data via MCP
2. Asks the LLM to reason about optimal settings
3. Calculates what a **traditional HA automation** would do
4. Logs both decisions for comparison

**Baseline automation rules (what most people set up):**
- Daytime (6am-10pm): 21°C
- Nighttime: 18°C
- Cold weather boost (outdoor < -10°C): +1°C
- Summer cooling (outdoor > 25°C): 24°C

**The AI can reason about things automations can't:**
- "It's cold now but warming up - skip the heating cycle"
- "Cold front coming tonight - pre-heat now while it's milder"
- "It's -8°C (not quite -10°C threshold) but windy - boost anyway"

### Web Dashboard

Access at `http://localhost:8080` to see:
- Current indoor/outdoor temperature
- Recent AI decisions with full reasoning
- **AI Override Rate** - how often AI chose differently than baseline
- Side-by-side comparison when decisions differ

### MCP Protocol Implementation

Both MCP servers implement the standard protocol with HTTP+SSE transport:
- `POST /mcp` - JSON-RPC endpoint for tool calls
- `GET /sse` - Server-Sent Events for streaming
- `GET /health` - Health check endpoint

### Multi-LLM Support

Switch between different LLM providers at runtime:

| Provider | Package | Default Model | Features |
|----------|---------|---------------|----------|
| **Ollama** (default) | Built-in | `llama3.1:8b` | Local, free, privacy |
| **OpenAI** | `pip install openai` | `gpt-4o` | Best reasoning |
| **Anthropic** | `pip install anthropic` | `claude-3-5-sonnet` | Great tool use |
| **Google** | `pip install google-generativeai` | `gemini-2.0-flash` | Fast, multimodal |

**Configuration:**
- Set `LLM_PROVIDER` and API keys in `.env` or dashboard Settings
- Switch providers in the Chat page dropdown to compare reasoning
- Agent reloads provider each evaluation cycle

**Install cloud providers:**
```bash
cd agent
pip install -e ".[all-llm]"  # Install all providers
# Or individually:
pip install -e ".[openai]"
pip install -e ".[anthropic]"
pip install -e ".[google]"
```

## 📋 Prerequisites

- **Docker** and **docker-compose**
- **Ollama** with a model pulled (for local LLM), OR API keys for cloud providers
- **Ecobee Account** with a registered thermostat and Developer access
- Network connectivity between containers and HA

## 🚀 Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url> mcp-iot-poc
cd mcp-iot-poc

# Copy environment template
cp .env.example .env
```

### 2. Edit Configuration

Edit `.env` with your details:

```bash
# Ecobee
ECOBEE_API_KEY=your_api_key_here
ECOBEE_REFRESH_TOKEN=your_refresh_token_here
ECOBEE_REFRESH_TOKEN=your_refresh_token_here
ECOBEE_THERMOSTAT_INDEX=0  # 0 for first thermostat, 1 for second, etc.
ECOBEE_MCP_URL=http://ecobee-mcp:8080

# Ollama
OLLAMA_URL=http://10.0.30.3:11434
OLLAMA_MODEL=ministral-3:14b

# Agent Settings
CHECK_INTERVAL_MINUTES=30
MIN_TEMP=17
MAX_TEMP=23
OLLAMA_TIMEOUT=120
LOG_FORMAT=text

# Dashboard Auth (Optional - enables login page)
DASHBOARD_USER=admin
DASHBOARD_PASS=secret

# LLM Provider Configuration
LLM_PROVIDER=ollama          # Options: ollama, openai, anthropic, google
# LLM_MODEL=                  # Leave empty for default

# Cloud LLM API Keys (optional)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...

# MCP Server Authentication (Optional - secures inter-service communication)
# MCP_AUTH_TOKEN=your_secret_token

# Location (for weather)
LATITUDE=45.35
LONGITUDE=-75.75
TIMEZONE=America/Toronto
```

### 3. Create Ecobee Credentials

Direct Ecobee integration requires a one-time authorization to get your API keys.

1. **Create App**: Log in to [Ecobee Developer Portal](https://www.ecobee.com/developers/), create a Consumer Key (Application). **Select "ecobee PIN" as the authorization method.** Copy the API Key.
2. **Run Setup Script**:
   ```bash
   pip install requests
   python3 servers/ecobee-mcp/tools/auth_setup.py <YOUR_API_KEY>
   ```
3. **Authorize**: Follow the script instructions to enter the PIN in "My Apps" on the Ecobee portal.
4. **Update Config**: The script will output your `ECOBEE_REFRESH_TOKEN`. Add it and your API Key to `.env`.

### 4. Verify Ollama

```bash
# Check Ollama is running
curl http://your-ollama-ip:11434/api/tags

# Pull model if needed
docker exec ollama ollama pull llama3.1:8b
```

### 5. Start the Stack

```bash
# Build and start all containers
docker-compose up -d

# Watch the logs
docker-compose logs -f agent

# View the dashboard
open http://localhost:8080
```

### 6. Deployment Setup (Komodo)

This project uses **Komodo** for automated deployments.

1.  **Configure Webhook in Komodo**:
    -   Go to the **"Repos"** (Repositories) section in Komodo.
    -   Select the repository connected to this project.
    -   Find the **Webhook URL** (usually under "Manage" or "Settings" for that Repo).
    -   *Note: If you configured the Stack directly without a shared Repo resource, check the Stack's "Source" or "Git" settings tab.*

2.  **Add Secret to GitHub**:
    -   Go to Repository Settings → Secrets and variables → Actions.
    -   Add a new repository secret:
        -   Name: `KOMODO_WEBHOOK_URL`
        -   Value: The URL you copied from Komodo.

Now, every push to `main` will automatically trigger a deployment.

## 📁 Project Structure

```
mcp-iot-poc/
├── docker-compose.yml          # Container orchestration
├── .env.example                # Configuration template
├── README.md                   # This file
│
├── servers/
│   ├── weather-mcp/            # Weather MCP Server
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/weather_mcp/
│   │       ├── __init__.py
│   │       └── server.py       # Open-Meteo API wrapper
│   │
│   └── ecobee-mcp/      # Ecobee MCP Server
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/ha_mcp/
│           ├── __init__.py
│           └── server.py       # HA REST API wrapper
│
├── agent/                      # Climate Agent
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/climate_agent/
│       ├── __init__.py
│       ├── main.py             # Agent loop & scheduler
│       ├── mcp_client.py       # MCP protocol client
│       ├── llm_provider.py     # Abstract LLM interface
│       ├── llm_factory.py      # Provider factory
│       ├── providers/          # LLM provider implementations
│       │   ├── ollama.py       # Ollama (local)
│       │   ├── openai.py       # OpenAI/ChatGPT
│       │   ├── anthropic.py    # Anthropic/Claude
│       │   └── google.py       # Google Gemini
│       ├── decision_logger.py  # SQLite logging
│       ├── web_dashboard.py    # FastAPI dashboard
│       └── tests/              # Unit tests
│
├── config/
│   └── system_prompt.md        # Agent's instructions
│
├── docs/
│   ├── AUTH0_PLAN.md           # Future Auth0 integration plan
│   ├── CODE_REVIEW.md          # Code review notes
│   └── mcp-iot-lunch-learn-plan.md
│
└── presentation/
    └── LUNCH_AND_LEARN.md      # Slide-by-slide presentation
```

## 🔧 MCP Server Details

### Weather MCP Server

**Tools provided:**

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_current_weather` | Current conditions | None |
| `get_forecast` | Hourly forecast | `hours` (integer 1-48, default 12) |

**Input Validation:**
The `get_forecast` tool includes robust input validation for the `hours` parameter:
- Handles malformed types (lists, strings, objects) gracefully
- Falls back to default (12 hours) with warning log
- Clamps values to valid range (1-48)

This prevents LLM tool-calling quirks from causing errors (e.g., when the model passes a list instead of an integer).

**Example response:**
```json
{
  "temperature_c": -5.2,
  "feels_like_c": -9.1,
  "humidity_percent": 72,
  "conditions": "Partly cloudy",
  "wind_speed_kmh": 15.5
}
```

### Home Assistant MCP Server

**Tools provided:**

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_thermostat_state` | Current state | None |
| `set_thermostat_temperature` | Set target temp | `temperature` (°C) |
| `set_hvac_mode` | Change mode | `hvac_mode` (heat/cool/auto/off) |
| `set_preset_mode` | Set preset | `preset_mode` (home/away/sleep) |

**Safety bounds enforced:** Temperature limited to MIN_TEMP - MAX_TEMP range (default 17-23°C).

## 🧪 Testing MCP Servers

```bash
# Health check
curl http://localhost:8081/health
curl http://localhost:8082/health

# List available tools
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'

# Call a tool
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_current_weather",
      "arguments": {}
    },
    "id": 1
  }'
```

## 📊 API Endpoints

### Dashboard & UI
- `GET /` - Web dashboard
- `GET /login` - Login page (if auth enabled)
- `GET /logout` - Logout and clear session
- `GET /prompts` - Prompt configuration page
- `GET /settings` - Agent settings page (Global Save available)
- `GET /chat` - Chat with agent (configurable LLM)

### Settings & Configuration
The Settings page (`/settings`) allows dynamic configuration of:
- **LLM Provider & Model**: Switch between Ollama, OpenAI, etc. on the fly.
- **API Keys**: Securely manage API keys for cloud providers (stored in local DB, overrides env vars).
- **Agent Parameters**: Adjust temperature bounds, check intervals, etc.
- **Global Save**: Save all settings at once with a single click.

### API
- `GET /health` - Health check
- `GET /api/decisions` - Recent decisions (JSON)
- `GET /api/stats` - Decision statistics
- `GET /api/comparison` - AI vs baseline comparison stats
- `GET /api/status` - Service health status
- `GET /api/security/stats` - Security event statistics
- `POST /api/security/test-injection` - Run security boundary tests

## 🧪 Testing & Quality

The project includes a comprehensive test suite using `pytest`.

```bash
# Run tests locally
cd agent
pip install -e ".[dev]"
pytest tests/ -v --cov=src --cov-report=term-missing
```

**Quality Features:**
- **CI/CD**: GitHub Actions pipeline runs tests on every push.
- **Coverage**: Minimum 45% code coverage enforced.
- **Type Hints**: Core modules are fully typed.
- **Linting**: Windsurf/Cursor rules enforced.

## 🏭 Production Readiness

### 🛡️ Security
- **MCP Authentication**: Optional bearer token auth between agent and MCP servers (`MCP_AUTH_TOKEN`).
- **Login Page**: Dashboard protected with session-based login (set `DASHBOARD_USER`/`PASS`).
- **Tool Safety Bounds**: Temperature limited to MIN_TEMP - MAX_TEMP (prevents hallucinated extremes).
- **Input Validation**: All LLM tool calls rigorously validated.
- **Security Dashboard**: View blocked actions, auth failures, and run injection tests.
- **Audit Logging**: Every decision and tool call logged to SQLite.

### 📊 Observability
- **Structured Logging**: Set `LOG_FORMAT=json` for machine-readable logs.
- **Health Checks**: All services have health endpoints.
- **Resource Limits**: Docker containers have CPU/memory limits.

### 🔄 Reliability
- **Retries**: HTTP calls use exponential backoff (via `tenacity`).
- **Timeouts**: All external calls have configurable timeouts (e.g. `OLLAMA_TIMEOUT`).
- **Graceful Shutdown**: Agent handles termination signals via `lifespan`.

## 🎓 How It Works

### Agent Decision Loop

Every 30 minutes (configurable):

1. **Gather Data**
   - Call `get_current_weather` via Weather MCP
   - Call `get_thermostat_state` via HA MCP
   - Call `get_forecast` for upcoming conditions

2. **AI Reasoning**
   - Send data to Ollama with system prompt
   - LLM reasons about optimal settings
   - LLM decides to adjust or maintain

3. **Baseline Comparison**
   - Calculate what rule-based automation would do
   - Compare decisions
   - Log difference if any

4. **Execute & Log**
   - If AI decides to change, call `set_thermostat_temperature`
   - Log everything to SQLite
   - Update dashboard

### System Prompt

The agent is instructed to:
- Maintain comfort (20-21°C daytime, 18°C night)
- Minimize energy usage
- Be predictive (pre-heat before cold snaps)
- Explain reasoning for all decisions

**Critical Tool Calling Rules** (to prevent LLM quirks):
- Call each tool only ONCE per evaluation
- Only use parameters defined in the tool schema
- Do NOT invent or hallucinate parameters
- If changing temperature, MUST call `set_thermostat_temperature`
- If NOT changing, do NOT call `set_thermostat_temperature`

See `agent/src/climate_agent/main.py` for the full system prompt.

## 🐛 Troubleshooting

### Agent can't connect to Ecobee

```bash
# Check ecobee-mcp logs for auth errors
docker-compose logs ecobee-mcp
```

Check:
- `ECOBEE_API_KEY` and `ECOBEE_REFRESH_TOKEN` are correct
- You authorized the app in the Ecobee portal
- The token hasn't expired (the server auto-refreshes, but if it's been offline for weeks you might need to re-auth)

### Ollama not responding

```bash
# Check Ollama is running
curl http://your-ollama-ip:11434/api/tags

# Check model is available
docker exec ollama ollama list
```

### MCP servers unhealthy

```bash
# Check individual server logs
docker-compose logs weather-mcp
docker-compose logs ecobee-mcp
```

### Database issues

The SQLite database is stored in a Docker volume. To reset:

```bash
docker-compose down
docker volume rm climate-agent-data
docker-compose up -d
```

## 📈 Demo Scenarios

These scenarios demonstrate where AI reasoning outperforms rule-based automation:

### Scenario 1: Pre-heating Before Cold Front

| Aspect | Baseline Automation | AI Agent |
|--------|---------------------|----------|
| **Situation** | It's -5°C outside, forecast shows -15°C in 3 hours | Same |
| **Decision** | NO_CHANGE (hasn't hit -10°C threshold yet) | SET_TEMPERATURE → 21.5°C |
| **Reasoning** | Rules only react to current state | "Pre-heating now to reduce recovery load when cold front arrives" |

### Scenario 2: Solar Gain Optimization

| Aspect | Baseline Automation | AI Agent |
|--------|---------------------|----------|
| **Situation** | Cold morning (-5°C), sunny day, forecast high of 8°C | Same |
| **Decision** | Cold boost to 22°C | NO_CHANGE (maintain 20°C) |
| **Reasoning** | Below threshold = boost | "Solar gain through south-facing windows will provide passive heating" |

### Scenario 3: Intelligent Night Transition

| Aspect | Baseline Automation | AI Agent |
|--------|---------------------|----------|
| **Situation** | 9:45pm, mild overnight forecast (2°C) | Same |
| **Decision** | Wait until 10pm, then set 18°C | SET_TEMPERATURE → 17.5°C now |
| **Reasoning** | Fixed schedule | "Mild forecast allows lower setback. Starting early since household is winding down." |

### Scenario 4: Interpolating Between Thresholds

| Aspect | Baseline Automation | AI Agent |
|--------|---------------------|----------|
| **Situation** | -8°C outside (between normal and cold threshold) | Same |
| **Decision** | Standard 21°C (hasn't hit -10°C) | SET_TEMPERATURE → 21.5°C |
| **Reasoning** | Binary threshold logic | "Wind chill makes it feel like -12°C. Slight boost warranted." |

## 🎤 Presentation Tips

When demoing this project:

1. **Start with the dashboard** - Show it's been running autonomously
2. **Highlight the override rate** - "The AI made different choices X% of the time"
3. **Pick a specific example** - Walk through the AI's reasoning
4. **Show the logs** - `docker-compose logs -f agent` during a live evaluation
5. **Explain MCP** - "This same pattern works for any tool - ServiceNow, databases, APIs"

**Key talking points:**
- MCP is becoming the standard for AI tool integration
- AI agents can reason about tradeoffs, not just follow rules
- Local LLMs (Ollama) make this practical and private
- The comparison feature proves the value objectively

**Small Model Quirks (llama3.1:8b):**
> "The 8B model works but sometimes gets confused with tool parameters. In production, you'd want input validation (which we have!) and possibly a larger model like qwen2.5:14b. This shows why model selection matters for agentic tasks."

Observable behaviors to point out:
- Duplicate tool calls with invented parameters
- Saying it will do something but not actually calling the tool
- Passing wrong types (e.g., list instead of integer)

## 🔮 Future Enhancements

- [ ] Occupancy detection integration
- [ ] Electricity time-of-use rate awareness  
- [ ] Multi-zone support
- [ ] Historical energy usage tracking
- [ ] Mobile notifications for significant decisions
- [ ] A/B testing mode (AI controls one day, baseline the next)

## 📚 Resources

- [MCP Specification](https://spec.modelcontextprotocol.io)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)

## 📄 License

MIT License - See LICENSE file for details.

## 🎤 Presentation

A complete lunch & learn presentation is available at [`presentation/LUNCH_AND_LEARN.md`](presentation/LUNCH_AND_LEARN.md).

**Topics covered:**
- What are AI Agents? (Chatbots vs Agents)
- What is MCP? (Protocol overview)
- Architecture deep dive (with diagrams)
- Security considerations (4 layers of protection)
- Gotchas & lessons learned
- Live demo script

---

**Built for a lunch & learn presentation demonstrating MCP and AI-powered IoT control.**
