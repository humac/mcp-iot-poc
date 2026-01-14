# MCP IoT Demo: AI-Powered Thermostat Control

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
│  │ Ollama      │  │ Weather MCP │  │ HA MCP      │  │ Agent      │  │
│  │             │◄─┤ Server      │◄─┤ Server      │◄─┤ Loop       │  │
│  │ llama3.1:8b │  │ :8081       │  │ :8082       │  │ :8080      │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │
│                          │                 │                        │
└──────────────────────────┼─────────────────┼────────────────────────┘
                           │                 │
                     Open-Meteo API    Home Assistant
                      (Internet)         (Local)
```

### Components

| Component | Port | Description |
|-----------|------|-------------|
| `weather-mcp` | 8081 | MCP server wrapping Open-Meteo weather API |
| `homeassistant-mcp` | 8082 | MCP server for Home Assistant climate control |
| `agent` | 8080 | Autonomous agent with web dashboard |
| `ollama` | 11434 | Local LLM inference (external) |

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

## 📋 Prerequisites

- **Docker** and **docker-compose**
- **Ollama** with `llama3.1:8b` model pulled
- **Home Assistant** with a climate entity (thermostat)
- Network connectivity between containers and HA

## 🚀 Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url> mcp-iot-demo
cd mcp-iot-demo

# Copy environment template
cp .env.example .env
```

### 2. Edit Configuration

Edit `.env` with your details:

```bash
# Home Assistant
HA_URL=http://10.0.20.5:8123
HA_TOKEN=your_long_lived_access_token_here
HA_ENTITY_ID=climate.my_ecobee

# Ollama
OLLAMA_URL=http://10.0.30.3:11434
OLLAMA_MODEL=llama3.1:8b

# Agent Settings
CHECK_INTERVAL_MINUTES=30
MIN_TEMP=17
MAX_TEMP=23

# Location (for weather)
LATITUDE=45.35
LONGITUDE=-75.75
TIMEZONE=America/Toronto
```

### 3. Create Home Assistant Token

In Home Assistant:
1. Go to your **Profile** (click your name in sidebar)
2. Scroll to **Long-Lived Access Tokens**
3. Click **Create Token**
4. Copy the token to your `.env` file

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

## 📁 Project Structure

```
mcp-iot-demo/
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
│   └── homeassistant-mcp/      # Home Assistant MCP Server
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
│       ├── ollama_client.py    # LLM integration
│       ├── decision_logger.py  # SQLite logging
│       └── web_dashboard.py    # FastAPI dashboard
│
├── config/
│   └── system_prompt.md        # Agent's instructions
│
└── presentation/               # Slides and diagrams
    └── diagrams/
```

## 🔧 MCP Server Details

### Weather MCP Server

**Tools provided:**

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_current_weather` | Current conditions | None |
| `get_forecast` | Hourly forecast | `hours` (1-48, default 12) |

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

### API
- `GET /health` - Health check
- `GET /api/decisions` - Recent decisions (JSON)
- `GET /api/stats` - Decision statistics
- `GET /api/comparison` - AI vs baseline comparison stats

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

See `config/system_prompt.md` for full prompt.

## 🐛 Troubleshooting

### Agent can't connect to HA

```bash
# Test from Docker network
docker exec climate-agent curl -s http://10.0.20.5:8123/api/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Check:
- HA_URL is correct and reachable
- HA_TOKEN is valid
- No firewall blocking the connection

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
docker-compose logs homeassistant-mcp
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

---

**Built for a lunch & learn presentation demonstrating MCP and AI-powered IoT control.**
