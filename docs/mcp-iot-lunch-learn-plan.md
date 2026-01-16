# MCP + IoT Lunch & Learn Implementation Plan

**Goal:** Build a working MCP-based AI agent that controls a thermostat based on weather forecasts, then present it as an educational demo  
**Timeline:** 4 weeks (Jan 14 - Feb 11, 2026)  
**Presentation Date:** Week of Feb 9, 2026

---

## Environment Details

| Component | Address | Notes |
|-----------|---------|-------|
| Home Assistant VM | `10.0.20.5:8123` | Proxmox VM |
| Thermostat Entity | `climate.my_ecobee` | Ecobee integration |
| Linux/Docker VM | `10.0.30.3` | Workload host |
| Ollama | `10.0.30.3:11434` | Container on Linux VM |
| LLM Model | `llama3.1:8b` | 24GB P40 GPU |
| Weather API | Open-Meteo | Free, no key required |
| Location | Ottawa area | ~45.35, -75.75 |

### Network Topology
```
┌─────────────────────────────────────────────────────────────────────┐
│  Proxmox Host                                                       │
│                                                                     │
│  ┌─────────────────────┐         ┌─────────────────────────────────┐│
│  │ Home Assistant VM   │         │ Linux VM (10.0.30.3)            ││
│  │ 10.0.20.5:8123      │◄───────►│                                 ││
│  │                     │         │  ┌─────────────────────────┐    ││
│  │ climate.my_ecobee   │         │  │ Docker Containers       │    ││
│  │                     │         │  │                         │    ││
│  └─────────────────────┘         │  │ ┌─────────────────────┐ │    ││
│                                  │  │ │ ollama (:11434)     │ │    ││
│                                  │  │ │ llama3.1:8b         │ │    ││
│                                  │  │ └─────────────────────┘ │    ││
│                                  │  │                         │    ││
│                                  │  │ ┌─────────────────────┐ │    ││
│                                  │  │ │ weather-mcp (:8081) │ │    ││
│                                  │  │ └─────────────────────┘ │    ││
│                                  │  │                         │    ││
│                                  │  │ ┌─────────────────────┐ │    ││
│                                  │  │ │ ha-mcp (:8082)      │ │    ││
│                                  │  │ └─────────────────────┘ │    ││
│                                  │  │                         │    ││
│                                  │  │ ┌─────────────────────┐ │    ││
│                                  │  │ │ agent (:8080)       │ │    ││
│                                  │  │ │ + web dashboard     │ │    ││
│                                  │  │ └─────────────────────┘ │    ││
│                                  │  │                         │    ││
│                                  │  └─────────────────────────┘    ││
│                                  └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Week 1: Foundation & First MCP Server (Jan 14-20)

### Learning Objectives
- Understand MCP protocol architecture (client/server, JSON-RPC, transports)
- Write a functional MCP server with HTTP+SSE transport (not stdio)
- Deploy MCP server as a Docker container

### Tasks

| Day | Task | Time Est | Deliverable |
|-----|------|----------|-------------|
| Tue-Wed | Read MCP spec & Python SDK docs (focus on HTTP transport) | 2 hrs | Notes on key concepts |
| Wed | Set up project structure on Linux VM | 1 hr | Git repo, docker-compose skeleton |
| Thu | Build "Hello World" MCP server with HTTP+SSE transport | 2.5 hrs | Container running on :8081 |
| Thu | Test MCP server with curl/manual requests | 30 min | Verified JSON-RPC works |
| Fri | Build Weather MCP server (wraps Open-Meteo API) | 3 hrs | `weather-mcp` container |
| Sat | Test weather MCP returns Ottawa forecast | 1 hr | Working forecast tool |
| Sun | Document learnings, clean up code | 1 hr | README updated |

### Key Difference: HTTP+SSE vs stdio
Since we're running in Docker (not Claude Desktop), we use **HTTP+SSE transport**:
- Server exposes HTTP endpoint
- Client connects via Server-Sent Events (SSE) for streaming
- JSON-RPC messages over HTTP POST

### Resources
- MCP Specification: https://spec.modelcontextprotocol.io
- Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP HTTP Transport: https://spec.modelcontextprotocol.io/specification/basic/transports/#http-with-sse
- Open-Meteo API: https://open-meteo.com/en/docs (free, no key needed)

### Milestone Checkpoint
✅ Weather MCP container running, can call `get_forecast` tool via HTTP and get real Ottawa data

---

## Week 2: Home Assistant MCP Server (Jan 21-27)

### Learning Objectives
- Integrate MCP with authenticated REST APIs
- Design tool schemas for IoT control
- Handle errors gracefully in MCP servers

### Pre-Work (do before Week 2 starts)
- [ ] Create HA long-lived access token: Profile → Security → Long-Lived Access Tokens
- [ ] Test HA REST API from Linux VM (see commands below)
- [ ] Verify network path: `curl http://10.0.20.5:8123/api/` from Linux VM

### Tasks

| Day | Task | Time Est | Deliverable |
|-----|------|----------|-------------|
| Tue | Test HA REST API from Linux VM | 1 hr | Working curl commands |
| Wed | Build HA MCP server - read operations | 3 hrs | `get_thermostat_state` tool |
| Thu | Add write operations | 2 hrs | `set_thermostat_temperature` tool |
| Thu | Add HVAC mode control | 1 hr | `set_hvac_mode` tool |
| Fri | Error handling & input validation | 1.5 hrs | Graceful failures |
| Sat | Deploy as Docker container | 1 hr | Running on :8082 |
| Sun | Integration test - call both MCP servers | 1 hr | Both responding correctly |

### Home Assistant REST API Commands (run from Linux VM)

```bash
# Set your token (replace with your actual token)
export HA_TOKEN="your_long_lived_token_here"

# Test API connectivity
curl -s -H "Authorization: Bearer $HA_TOKEN" \
     http://10.0.20.5:8123/api/ | jq

# Get thermostat state
curl -s -H "Authorization: Bearer $HA_TOKEN" \
     http://10.0.20.5:8123/api/states/climate.my_ecobee | jq

# Set temperature (test with caution!)
curl -X POST \
     -H "Authorization: Bearer $HA_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"entity_id": "climate.my_ecobee", "temperature": 21}' \
     http://10.0.20.5:8123/api/services/climate/set_temperature

# Set HVAC mode
curl -X POST \
     -H "Authorization: Bearer $HA_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"entity_id": "climate.my_ecobee", "hvac_mode": "heat"}' \
     http://10.0.20.5:8123/api/services/climate/set_hvac_mode
```

### Ecobee-Specific Attributes
Your `climate.my_ecobee` entity likely exposes:
- `current_temperature` - current reading
- `temperature` - target setpoint (or `target_temp_high`/`target_temp_low` for auto mode)
- `hvac_mode` - off, heat, cool, auto
- `hvac_action` - idle, heating, cooling
- `preset_mode` - home, away, sleep (Ecobee comfort settings)

### Milestone Checkpoint
✅ Both MCP containers running, can read thermostat state and weather forecast via HTTP

---

## Week 3: Agent Loop & Demo Polish (Jan 28 - Feb 3)

### Learning Objectives
- Build an MCP client that connects to multiple servers
- Integrate Ollama for local LLM inference with tool calling
- Create a decision logging system for demo

### Tasks

| Day | Task | Time Est | Deliverable |
|-----|------|----------|-------------|
| Tue | Build basic agent loop - connects to both MCP servers | 2.5 hrs | Agent discovers tools |
| Wed | Integrate Ollama tool calling | 2.5 hrs | Agent can invoke tools |
| Thu | Add decision logging (SQLite or JSON) | 1.5 hrs | Persisted decision history |
| Thu | Add simple web dashboard (FastAPI + HTML) | 2 hrs | View decisions at :8080 |
| Fri | Create system prompt for energy optimization | 1.5 hrs | Good decision-making |
| Sat | Add scheduling (run every 30 min) | 1 hr | Autonomous operation |
| Sat | Safety bounds - min/max temp limits | 1 hr | Won't set crazy values |
| Sun | Full dry run - let it run for a few hours | 1 hr | Verify stable operation |

### Agent Architecture
```
┌────────────────────────────────────────────────────────────┐
│  Agent Container                                           │
│                                                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Scheduler    │───►│ MCP Client   │───►│ Ollama       │  │
│  │ (APScheduler │    │              │    │ Integration  │  │
│  │  or cron)    │    │ - weather    │    │              │  │
│  └──────────────┘    │ - HA         │    │ llama3.1:8b  │  │
│                      └──────────────┘    └──────────────┘  │
│         │                                       │          │
│         ▼                                       ▼          │
│  ┌──────────────┐                      ┌──────────────┐    │
│  │ Web Dashboard│                      │ Decision Log │    │
│  │ :8080        │◄─────────────────────│ (SQLite)     │    │
│  └──────────────┘                      └──────────────┘    │
└────────────────────────────────────────────────────────────┘
```

### Ollama Tool Calling Format
```python
import requests

response = requests.post(
    "http://10.0.30.3:11434/api/chat",
    json={
        "model": "llama3.1:8b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Evaluate current conditions and recommend thermostat action"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_forecast",
                    "description": "Get weather forecast for Ottawa",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours": {"type": "integer", "description": "Hours of forecast to retrieve"}
                        }
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_thermostat_state",
                    "description": "Get current thermostat state",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_thermostat_temperature",
                    "description": "Set thermostat target temperature",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "temperature": {"type": "number", "description": "Target temperature in Celsius"}
                        },
                        "required": ["temperature"]
                    }
                }
            }
        ],
        "stream": False
    }
)
```

### Agent Prompt Architecture

The agent uses two prompts that work together:

| Prompt | Purpose | When Sent |
|--------|---------|-----------|
| **system_prompt** | Sets up agent identity, rules, available tools, and decision-making logic | Once at conversation start |
| **user_task** | The trigger that tells the agent to do its job | Every evaluation cycle (e.g., every 15 min) |

**Flow:**
```
┌─────────────────────────────────────────────────────────────────┐
│  system_prompt (sent once)                                      │
│  "You are an energy optimization agent... here are your tools,  │
│   your goals, your decision rules, examples..."                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  user_task (sent every cycle)                                   │
│  "Evaluate the current weather and thermostat state.            │
│   Decide if any adjustments should be made..."                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Agent executes tools
                    Makes decision
                    Returns response
```

**Think of it like:**
- `system_prompt` = "Here's who you are and how to think"
- `user_task` = "Now do your job"

Both prompts are stored in the database and editable via the web dashboard. This allows tuning the agent's behavior without code changes.

### System Prompt for Energy Optimization Agent
```markdown
You are an energy optimization agent for a home in Ottawa, Canada.

## Available Tools
- get_forecast: Get hourly weather forecast (temperature, conditions)
- get_thermostat_state: Get current thermostat setting and temperature
- set_thermostat_temperature: Adjust the thermostat setpoint

## Your Goals
1. Maintain comfort: Target 20-21°C when occupied (6am-11pm), 18°C overnight
2. Minimize energy: Use weather forecast to avoid unnecessary heating/cooling
3. Be predictive: Pre-heat before cold snaps, let temp drift if warming trend

## Decision Rules
- If current temp is comfortable AND forecast shows stable/warming → do nothing
- If cold front coming in next 2-4 hours → consider pre-heating
- If sunny and warming → can lower setpoint slightly
- Never set below 17°C or above 23°C

## Response Format
1. First, gather data by calling get_forecast and get_thermostat_state
2. Analyze the situation
3. Decide: ADJUST or NO_CHANGE
4. If ADJUST, call set_thermostat_temperature with your target
5. Explain your reasoning briefly
```

### Demo Scenarios to Prepare

1. **Status Check**: Agent reports current state, decides no change needed
2. **Pre-heating**: Cold front coming, agent pre-heats proactively
3. **Energy Saving**: Warm sunny day, agent lowers setpoint
4. **Night Setback**: Evening check, agent reduces for overnight
5. **Override Recovery**: Manual change detected, agent adapts

### Demo Talking Points: AI vs Rule-Based Automation

**Key Example: Nighttime Override**
When it's after 10pm, the baseline rule says: "It's nighttime → set to 18°C". That's all it considers.

But the AI looked at the *actual conditions*:
- Indoor temp: 22.3°C
- Current setpoint: 22°C
- Outdoor temp: -3.2°C (feels like -8.4°C)
- Forecast: Dropping to -13.8°C by midnight

**AI's reasoning:** "The house is at 22°C. If I drop to 18°C right now with a cold front coming, the furnace will have to work hard later tonight to recover. Better to let the house naturally cool down gradually rather than forcing a 4-degree drop right before temps plummet."

**Why this is smarter:**
- Baseline: Drop 22°C → 18°C immediately at 10pm → house cools rapidly → at midnight when it's -14°C outside, furnace kicks in hard = more energy
- AI: Keep setpoint, let house coast down naturally → furnace maintains from a warmer starting point = less energy

**Highlight for audience:** "The AI overrode the rigid schedule because it considered the forecast. That's the difference between rule-based automation and contextual AI reasoning."

### Real Example: Observed January 14, 2026 at 10:53 PM

**Conditions:**
- Time: 10:53 PM (after nighttime threshold)
- Indoor temp: 21.3°C (target: 21.5°C)
- Outdoor temp: -5.7°C (feels like -11.9°C due to wind)
- Forecast: Dropping to -10.1°C with moderate snow

**Baseline would do:** SET_TEMPERATURE → 18°C (time_based_schedule)

**AI chose:** NO_CHANGE (keep at 21.5°C)

**AI's reasoning:** "The house is warm at 21.3°C. With a cold front approaching (-10°C with snow), dropping to 18°C now would cause rapid cooling. The furnace would then have to work hard at midnight to recover. Better to maintain the current setpoint and let the house coast naturally."

**Energy impact:**
- Baseline: 21.5°C → 18°C drop at 10pm → rapid cooling → furnace struggles at midnight = more energy
- AI: Maintain 21.5°C → gradual natural cooling → furnace maintains from warmer starting point = less energy

### Small Model Quirks (llama3.1:8b)

**Good talking point for the demo:**
> "The 8B model works but sometimes gets confused with tool parameters. You'll notice it occasionally calls tools twice or hallucinates arguments that don't exist. In production, you'd want input validation and possibly a larger model like qwen2.5:14b. This shows why model selection matters for agentic tasks."

**Observed behaviors:**
- Duplicate tool calls with invented parameters
- Saying it will do something but not actually calling the tool
- Passing wrong types (e.g., list instead of integer for `hours`)

**This is actually a feature for the demo** - it shows real-world LLM behavior and the importance of:
1. Input validation in your MCP servers
2. Logging to understand what the agent actually did
3. Model selection for production deployments

### Milestone Checkpoint
✅ Agent running autonomously, making logged decisions every 30 minutes

---

## Week 4: Presentation Creation & Rehearsal (Feb 4-10)

### Tasks

| Day | Task | Time Est | Deliverable |
|-----|------|----------|-------------|
| Tue | Create slide deck - outline and structure | 2 hrs | 15-20 slide outline |
| Wed | Write slide content - MCP explainer section | 2 hrs | Technical slides done |
| Wed | Create architecture diagrams | 1 hr | Clean visuals |
| Thu | Write slide content - demo section and enterprise angle | 1.5 hrs | Full deck draft |
| Fri | Rehearsal #1 - solo run-through with timer | 45 min | Timing notes |
| Sat | Refine slides based on rehearsal | 1 hr | Polished deck |
| Sun | Rehearsal #2 - ideally with a friend/colleague | 45 min | Feedback incorporated |
| Mon | Final prep - backup plans, test equipment | 1 hr | Ready to present |
| Tue-Wed | **PRESENT** 🎉 | 30 min | Success! |

### Slide Deck Structure

1. **Title Slide** - "Teaching Your Building to Think: AI Agents Meet IoT"
2. **The Problem** - Rule-based automation is brittle
3. **The Vision** - AI that reasons about context
4. **What is MCP?** - The "USB-C for AI tools"
5. **MCP Architecture** - Client/Server/Transport diagram
6. **Why MCP Matters** - Anthropic, OpenAI adoption, standardization
7. **Our Demo Architecture** - Weather + HA + Claude
8. **Code Walkthrough** - Show the MCP server (simplified)
9. **Live Demo** - The main event
10. **What Just Happened** - Recap the tool calls
11. **Enterprise Applications** - ServiceNow, monitoring, provisioning
12. **Getting Started** - Resources for the audience
13. **Q&A**

### Backup Plans
- **HA down**: Have screenshots/video of a successful run
- **Network issues**: Mobile hotspot ready
- **Claude API issues**: Pre-recorded video backup
- **Time crunch**: Know which slides to skip

### Presentation Tips
- Keep Claude Desktop and HA dashboard side-by-side on screen
- Use a terminal window showing MCP server logs (makes it feel "real")
- Have the audience suggest a scenario for the "freestyle" demo
- End with "you can build this in a weekend" to encourage experimentation

---

## Environment Setup Checklist

### Linux VM (10.0.30.3)
- [ ] Docker and docker-compose installed
- [ ] Ollama container running with `llama3.1:8b` pulled
- [ ] Git installed for repo management
- [ ] Python 3.11+ available (for local testing)
- [ ] Can reach HA at 10.0.20.5:8123
- [ ] Can reach Ollama at localhost:11434

### Home Assistant (10.0.20.5)
- [ ] Long-lived access token created
- [ ] `climate.my_ecobee` entity accessible
- [ ] REST API enabled (default)
- [ ] Tested API calls from Linux VM

### Ollama
```bash
# Verify Ollama is running
curl http://10.0.30.3:11434/api/tags

# Pull the model if not present
docker exec <ollama-container-name> ollama pull llama3.1:8b

# Test inference
curl http://10.0.30.3:11434/api/chat -d '{
  "model": "llama3.1:8b",
  "messages": [{"role": "user", "content": "Say hello"}],
  "stream": false
}'
```

### Presentation Day
- [ ] Laptop with browser and SSH access to Linux VM
- [ ] HDMI/USB-C adapter for projector
- [ ] Mobile hotspot as network backup
- [ ] Demo dashboard URL bookmarked (http://10.0.30.3:8080)
- [ ] Terminal ready to show logs: `docker-compose logs -f agent`
- [ ] HA dashboard open in browser tab
- [ ] Backup demo video on local drive

---

## Code Repository Structure

```
mcp-iot-poc/
├── README.md
├── docker-compose.yml
├── .env.example                    # HA_TOKEN, etc.
│
├── servers/
│   ├── weather-mcp/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── weather_mcp/
│   │           ├── __init__.py
│   │           └── server.py       # HTTP+SSE MCP server
│   │
│   └── homeassistant-mcp/
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/
│           └── ha_mcp/
│               ├── __init__.py
│               └── server.py       # HTTP+SSE MCP server
│
├── agent/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       └── climate_agent/
│           ├── __init__.py
│           ├── main.py             # Entry point, scheduler
│           ├── mcp_client.py       # Connects to MCP servers
│           ├── ollama_client.py    # Tool calling with Ollama
│           ├── decision_logger.py  # SQLite logging
│           └── web_dashboard.py    # FastAPI dashboard
│
├── config/
│   └── system_prompt.md            # Agent system prompt
│
└── presentation/
    ├── slides/
    └── diagrams/
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  weather-mcp:
    build: ./servers/weather-mcp
    ports:
      - "8081:8080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  homeassistant-mcp:
    build: ./servers/homeassistant-mcp
    ports:
      - "8082:8080"
    environment:
      - HA_URL=http://10.0.20.5:8123
      - HA_TOKEN=${HA_TOKEN}
      - HA_ENTITY_ID=climate.my_ecobee
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  agent:
    build: ./agent
    ports:
      - "8080:8080"  # Web dashboard
    environment:
      - OLLAMA_URL=http://10.0.30.3:11434
      - OLLAMA_MODEL=llama3.1:8b
      - WEATHER_MCP_URL=http://weather-mcp:8080
      - HA_MCP_URL=http://homeassistant-mcp:8080
      - CHECK_INTERVAL_MINUTES=30
      - MIN_TEMP=17
      - MAX_TEMP=23
    volumes:
      - agent-data:/app/data  # Persist decision logs
    depends_on:
      - weather-mcp
      - homeassistant-mcp
    restart: unless-stopped

volumes:
  agent-data:
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| HA API changes break demo | Low | High | Pin HA version, test day before |
| Weather API rate limited | Low | Medium | Cache responses, have backup data |
| Network issues during demo | Medium | High | Mobile hotspot, local fallback |
| Claude gives unexpected response | Medium | Medium | Rehearse edge cases, have reset plan |
| Run over time | Medium | Low | Know what to cut, practice with timer |
| Audience questions stump you | Medium | Low | "Great question, let's discuss after" |

---

## Success Criteria

**Technical**
- [ ] Weather MCP server returns accurate Ottawa forecast via HTTP
- [ ] HA MCP server reads and writes `climate.my_ecobee` state
- [ ] Agent successfully chains tool calls through Ollama
- [ ] Agent runs autonomously every 30 minutes
- [ ] Web dashboard shows decision history
- [ ] Demo runs 3x consecutively without failure

**Presentation**
- [ ] Audience understands what MCP is and why it matters
- [ ] Live demo works smoothly (dashboard + logs visible)
- [ ] Can show historical decisions made by the agent
- [ ] At least 2-3 good questions from audience
- [ ] Positive feedback / interest in learning more

---

## Notes & Questions to Resolve

- [ ] Get HA long-lived access token created
- [ ] Confirm `llama3.1:8b` is pulled in Ollama
- [ ] Schedule lunch & learn slot with team
- [ ] Decide if sharing code repo internally after
- [ ] Any company-specific use cases to highlight? (ServiceNow, monitoring, etc.)

---

## Quick Start Commands

```bash
# SSH to Linux VM
ssh user@10.0.30.3

# Clone repo (once created)
git clone <your-repo-url> mcp-iot-poc
cd mcp-iot-poc

# Copy env file and add your HA token
cp .env.example .env
nano .env  # Add HA_TOKEN=your_token_here

# Start everything
docker-compose up -d

# Watch agent logs
docker-compose logs -f agent

# View dashboard
# Open browser to http://10.0.30.3:8080
```
