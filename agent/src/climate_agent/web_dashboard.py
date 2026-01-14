"""
Web Dashboard

FastAPI-based dashboard for viewing agent decisions and status.
"""

import os
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .decision_logger import DecisionLogger

app = FastAPI(title="Climate Agent Dashboard")

# Templates
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# We'll use inline HTML since we're in a container
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Climate Agent Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold text-gray-800 mb-2">🌡️ Climate Agent Dashboard</h1>
        <p class="text-gray-600 mb-8">AI-powered thermostat control vs traditional automation</p>
        
        <!-- Stats Cards -->
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <div class="text-sm text-gray-500">Total Decisions</div>
                <div class="text-3xl font-bold text-blue-600">{{ stats.total_decisions }}</div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="text-sm text-gray-500">Today</div>
                <div class="text-3xl font-bold text-green-600">{{ stats.decisions_today }}</div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="text-sm text-gray-500">AI Override Rate</div>
                <div class="text-3xl font-bold text-purple-600">{{ comparison.ai_override_rate }}%</div>
                <div class="text-xs text-gray-400">Times AI chose differently</div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="text-sm text-gray-500">Different Decisions</div>
                <div class="text-3xl font-bold text-orange-600">{{ comparison.different_decisions }}</div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="text-sm text-gray-500">Status</div>
                <div class="text-3xl font-bold text-green-500">● Running</div>
            </div>
        </div>
        
        <!-- Current State -->
        <div class="bg-white rounded-lg shadow p-6 mb-8" id="current-state">
            <h2 class="text-xl font-semibold mb-4">Current State</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                    <div class="text-sm text-gray-500">Indoor Temp</div>
                    <div class="text-2xl font-bold">{{ current_state.current_temp }}°C</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500">Target Temp</div>
                    <div class="text-2xl font-bold">{{ current_state.target_temp }}°C</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500">HVAC Mode</div>
                    <div class="text-2xl font-bold capitalize">{{ current_state.hvac_mode }}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500">Outside Temp</div>
                    <div class="text-2xl font-bold">{{ current_state.outside_temp }}°C</div>
                </div>
            </div>
        </div>
        
        <!-- Recent Decisions with Comparison -->
        <div class="bg-white rounded-lg shadow">
            <div class="px-6 py-4 border-b">
                <h2 class="text-xl font-semibold">Recent Decisions</h2>
                <p class="text-sm text-gray-500">Comparing AI agent vs what HA automation would do</p>
            </div>
            <div class="divide-y" id="decisions-list">
                <!-- Decisions inserted here -->
            </div>
        </div>
        
        <!-- Baseline Rules Reference -->
        <div class="mt-8 bg-gray-50 rounded-lg p-6">
            <h3 class="font-semibold text-gray-700 mb-2">📋 Baseline HA Automation Rules (for comparison)</h3>
            <div class="text-sm text-gray-600 grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>• Daytime (6am-10pm): 21°C</div>
                <div>• Nighttime: 18°C</div>
                <div>• Cold boost (outdoor &lt; -10°C): +1°C</div>
                <div>• Summer cooling (outdoor &gt; 25°C): 24°C</div>
            </div>
        </div>
        
        <div class="mt-8 text-center text-gray-500 text-sm">
            Auto-refreshes every 60 seconds | Last updated: {{ now }}
        </div>
    </div>
</body>
</html>
"""


async def get_dashboard_html(request: Request) -> HTMLResponse:
    """Render the dashboard."""
    logger = DecisionLogger()
    
    try:
        decisions = await logger.get_recent_decisions(limit=20)
        stats = await logger.get_decision_stats()
        comparison = await logger.get_comparison_stats()
    except Exception as e:
        decisions = []
        stats = {
            "total_decisions": 0,
            "decisions_today": 0,
            "success_rate": 100,
            "action_breakdown": {},
        }
        comparison = {
            "total_compared": 0,
            "matching_decisions": 0,
            "different_decisions": 0,
            "ai_override_rate": 0,
            "recent_differences": [],
        }
    
    # Get current state from most recent decision
    current_state = None
    if decisions and decisions[0].get("thermostat_state"):
        ts = decisions[0]["thermostat_state"]
        ws = decisions[0].get("weather_data") or {}  # Handle None case
        current_state = {
            "current_temp": ts.get("current_temperature", "?"),
            "target_temp": ts.get("target_temperature", "?"),
            "hvac_mode": ts.get("hvac_mode", "?"),
            "outside_temp": ws.get("temperature_c", "?") if ws else "?",
        }
    
    # Build HTML
    html = DASHBOARD_HTML
    
    # Replace stats
    html = html.replace("{{ stats.total_decisions }}", str(stats["total_decisions"]))
    html = html.replace("{{ stats.decisions_today }}", str(stats["decisions_today"]))
    html = html.replace("{{ comparison.ai_override_rate }}", str(comparison["ai_override_rate"]))
    html = html.replace("{{ comparison.different_decisions }}", str(comparison["different_decisions"]))
    html = html.replace("{{ now }}", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    # Handle current state
    if current_state:
        html = html.replace("{{ current_state.current_temp }}", str(current_state["current_temp"]))
        html = html.replace("{{ current_state.target_temp }}", str(current_state["target_temp"]))
        html = html.replace("{{ current_state.hvac_mode }}", str(current_state["hvac_mode"]))
        html = html.replace("{{ current_state.outside_temp }}", str(current_state["outside_temp"]))
    else:
        html = html.replace("{{ current_state.current_temp }}", "?")
        html = html.replace("{{ current_state.target_temp }}", "?")
        html = html.replace("{{ current_state.hvac_mode }}", "?")
        html = html.replace("{{ current_state.outside_temp }}", "?")
    
    # Build decisions list HTML
    decisions_html = ""
    for decision in decisions:
        action = decision.get("action", "UNKNOWN")
        timestamp = decision.get("timestamp", "")[:19]
        reasoning = decision.get("reasoning", "No reasoning provided")
        ai_temp = decision.get("ai_temperature")
        baseline_action = decision.get("baseline_action")
        baseline_temp = decision.get("baseline_temperature")
        baseline_rule = decision.get("baseline_rule", "")
        decisions_match = decision.get("decisions_match")
        tool_count = len(decision.get("tool_calls", []) or [])
        
        # Determine badge color for AI decision
        if action == "NO_CHANGE":
            ai_badge_class = "bg-gray-100 text-gray-800"
        elif action == "SET_TEMPERATURE":
            ai_badge_class = "bg-blue-100 text-blue-800"
        elif action == "ERROR":
            ai_badge_class = "bg-red-100 text-red-800"
        else:
            ai_badge_class = "bg-green-100 text-green-800"
        
        # Format AI decision text
        ai_temp_str = f" → {ai_temp}°C" if ai_temp else ""
        
        # Build comparison section
        comparison_html = ""
        if baseline_action:
            baseline_temp_str = f" → {baseline_temp}°C" if baseline_temp else ""
            
            if decisions_match == 0:
                # Decisions differ - highlight this
                comparison_html = f"""
                <div class="mt-3 p-3 bg-orange-50 rounded-lg border border-orange-200">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-orange-600 font-semibold">⚡ AI Override</span>
                    </div>
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="text-gray-500">Baseline would:</span>
                            <span class="font-medium">{baseline_action}{baseline_temp_str}</span>
                            <span class="text-gray-400 text-xs">({baseline_rule})</span>
                        </div>
                        <div>
                            <span class="text-gray-500">AI chose:</span>
                            <span class="font-medium text-blue-600">{action}{ai_temp_str}</span>
                        </div>
                    </div>
                </div>
                """
            else:
                # Decisions match
                comparison_html = f"""
                <div class="mt-2 text-sm text-gray-500">
                    ✓ Matches baseline automation ({baseline_rule})
                </div>
                """
        
        tool_info = f'<span class="text-gray-400 text-sm ml-2">({tool_count} tool calls)</span>' if tool_count else ""
        
        decisions_html += f"""
        <div class="px-6 py-4 hover:bg-gray-50">
            <div class="flex justify-between items-start mb-2">
                <div class="flex items-center gap-2">
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium {ai_badge_class}">
                        {action}{ai_temp_str}
                    </span>
                    {tool_info}
                </div>
                <span class="text-sm text-gray-500">{timestamp}</span>
            </div>
            <p class="text-gray-700">{reasoning[:300]}{"..." if len(reasoning) > 300 else ""}</p>
            {comparison_html}
        </div>
        """
    
    if not decisions_html:
        decisions_html = """
        <div class="px-6 py-8 text-center text-gray-500">
            No decisions yet. The agent will make its first decision soon.
        </div>
        """
    
    # Insert decisions into HTML
    html = html.replace('<!-- Decisions inserted here -->', decisions_html)
    
    return HTMLResponse(content=html)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard home page."""
    return await get_dashboard_html(request)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "climate-agent"}


@app.get("/api/decisions")
async def api_decisions(limit: int = 20):
    """API endpoint for decisions."""
    logger = DecisionLogger()
    return await logger.get_recent_decisions(limit=limit)


@app.get("/api/stats")
async def api_stats():
    """API endpoint for stats."""
    logger = DecisionLogger()
    return await logger.get_decision_stats()


@app.get("/api/comparison")
async def api_comparison():
    """API endpoint for AI vs baseline comparison stats."""
    logger = DecisionLogger()
    return await logger.get_comparison_stats()
