# Occupancy Detection - Code Snippets

Exact code to add for occupancy detection. Copy-paste ready.

---

## File 1: `servers/homeassistant-mcp/src/ha_mcp/server.py`

### Add to `list_tools()` function (after existing tools):

```python
        Tool(
            name="get_occupancy_state",
            description="Get occupancy status from thermostat sensors. Returns whether home is occupied and minutes since last motion detected.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
```

### Add to `call_tool()` function (after existing elif blocks):

```python
        elif name == "get_occupancy_state":
            # Query the occupancy binary sensor
            entity_base = HA_ENTITY_ID.replace("climate.", "")
            occupancy_entity = f"binary_sensor.{entity_base}_occupancy"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{HA_URL}/api/states/{occupancy_entity}",
                    headers={"Authorization": f"Bearer {HA_TOKEN}"},
                    timeout=10.0,
                )
                
                if response.status_code == 404:
                    return [TextContent(
                        type="text",
                        text=json.dumps({"error": f"Occupancy sensor not found: {occupancy_entity}"})
                    )]
                
                response.raise_for_status()
                state = response.json()
            
            # Calculate minutes since last motion
            last_motion = state.get("attributes", {}).get("last_motion")
            minutes_since_motion = None
            if last_motion:
                try:
                    from datetime import datetime
                    last_motion_dt = datetime.fromisoformat(last_motion.replace("Z", "+00:00"))
                    now = datetime.now(last_motion_dt.tzinfo)
                    minutes_since_motion = round((now - last_motion_dt).total_seconds() / 60)
                except Exception:
                    pass
            
            result = {
                "currently_occupied": state.get("state") == "on",
                "minutes_since_last_motion": minutes_since_motion,
                "sensor_state": state.get("state"),
                "sensor_entity": occupancy_entity,
            }
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
```

---

## File 2: `agent/src/climate_agent/main.py`

### Add to `tools` list in `run_evaluation()` (after `set_thermostat_temperature`):

```python
            {
                "type": "function",
                "function": {
                    "name": "get_occupancy_state",
                    "description": "Get occupancy status - whether home is occupied and minutes since last motion",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
```

### Add to `execute_tool()` method (add to `ha_tools` set):

```python
        ha_tools = {"get_thermostat_state", "set_thermostat_temperature", "set_hvac_mode", "set_preset_mode", "get_occupancy_state"}
```

### Update system prompt (add to `## Available Tools` section):

```python
- get_occupancy_state: Get whether home is occupied and minutes since last motion
```

### Add to system prompt (new section after `## Decision Rules`):

```python
## Occupancy-Aware Rules

CRITICAL: Distinguish between "away" and "asleep":
- Night (11pm-6am) + no motion = ASLEEP, not away → maintain 18°C for comfort
- Day (8am-5pm) + no motion for 30+ min = AWAY → setback to 16°C
- Evening (5pm-11pm) + no motion for 60+ min = possibly away, be cautious

Decision matrix:
| Time of Day | Occupied | Minutes Since Motion | Target |
|-------------|----------|---------------------|--------|
| Night       | no       | any                 | 18°C (asleep) |
| Morning     | no       | < 30                | 20°C (waking) |
| Morning     | no       | > 60                | 18°C (still asleep) |
| Day         | no       | > 30                | 16°C (away) |
| Day         | yes      | any                 | 21°C |
| Evening     | no       | > 60                | verify/16°C |
| Evening     | yes      | any                 | 21°C |

IMPORTANT: Always call get_occupancy_state along with other data gathering tools.
```

---

## File 3: `agent/src/climate_agent/main.py` (BaselineAutomation class)

### Add to `get_settings()` method:

```python
            "away_threshold_minutes": int(await self.logger.get_setting("baseline_away_threshold", "30", "Minutes of no motion to consider 'away'", "Baseline")),
            "away_temp": float(await self.logger.get_setting("baseline_away_temp", "16.0", "Temperature when away (°C)", "Baseline")),
```

### Update `get_baseline_decision()` signature to accept occupancy:

```python
    async def get_baseline_decision(
        self,
        current_hour: int,
        outdoor_temp: float,
        indoor_temp: float,
        current_setpoint: float,
        occupancy_data: dict = None,  # NEW PARAMETER
    ) -> dict:
```

### Add occupancy logic to `get_baseline_decision()` (after getting settings):

```python
        # Occupancy-based rules
        if occupancy_data:
            is_occupied = occupancy_data.get("currently_occupied", True)
            minutes_since_motion = occupancy_data.get("minutes_since_last_motion")
            
            # Night time (11pm-6am): no motion = asleep, not away
            is_night = current_hour >= 23 or current_hour < 6
            
            if not is_occupied and not is_night:
                # Daytime with no occupancy
                if minutes_since_motion and minutes_since_motion > settings["away_threshold_minutes"]:
                    return {
                        "action": "SET_TEMPERATURE",
                        "temperature": settings["away_temp"],
                        "rule_triggered": "away_mode",
                        "reasoning": f"No motion for {minutes_since_motion} min during day - setting away temp {settings['away_temp']}°C",
                    }
```

---

## File 4: `.env.example`

### Add at end:

```bash
# Occupancy Detection
# OCCUPANCY_AWAY_MINUTES=30
# OCCUPANCY_AWAY_TEMP=16
```

---

## File 5: `agent/src/climate_agent/web_dashboard.py` (DASHBOARD_HTML)

### Add to "Current State" section (after "Outside Temp"):

```html
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Occupancy</div>
                    <div class="text-2xl font-bold text-gray-800 dark:text-gray-100" id="occupancy-status">--</div>
                </div>
```

---

## Summary

| File | What to Add |
|------|-------------|
| `ha_mcp/server.py` | New `get_occupancy_state` tool (list + call) |
| `main.py` | Tool in LLM tools list, update ha_tools set |
| `main.py` | System prompt occupancy rules |
| `main.py` | BaselineAutomation occupancy logic |
| `.env.example` | Occupancy config vars |
| `web_dashboard.py` | Occupancy display in dashboard |

