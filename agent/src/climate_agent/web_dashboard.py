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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
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

        <!-- Charts Section -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- Temperature Timeline Chart -->
            <div class="bg-white rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4">📈 Temperature Timeline</h2>
                <div style="height: 300px;">
                    <canvas id="tempChart"></canvas>
                </div>
            </div>

            <!-- Daily Override Rate Chart -->
            <div class="bg-white rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4">📊 Daily AI Override Rate</h2>
                <div style="height: 300px;">
                    <canvas id="overrideChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Hourly Analysis -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4">🕐 AI Overrides by Hour of Day</h2>
            <div style="height: 250px;">
                <canvas id="hourlyChart"></canvas>
            </div>
            <p class="text-sm text-gray-500 mt-2">Shows when AI most often disagrees with baseline automation</p>
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

    <script>
        // Timeline data from server
        const timelineData = {{ timeline_json }};
        const dailyData = {{ daily_json }};
        const hourlyData = {{ hourly_json }};

        // Temperature Timeline Chart
        if (timelineData.length > 0) {
            const tempCtx = document.getElementById('tempChart').getContext('2d');
            new Chart(tempCtx, {
                type: 'line',
                data: {
                    labels: timelineData.map(d => d.timestamp),
                    datasets: [
                        {
                            label: 'Indoor Temp',
                            data: timelineData.map(d => d.indoor_temp),
                            borderColor: 'rgb(59, 130, 246)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.3,
                            fill: false,
                        },
                        {
                            label: 'Outdoor Temp',
                            data: timelineData.map(d => d.outdoor_temp),
                            borderColor: 'rgb(34, 197, 94)',
                            backgroundColor: 'rgba(34, 197, 94, 0.1)',
                            tension: 0.3,
                            fill: false,
                        },
                        {
                            label: 'Target Temp',
                            data: timelineData.map(d => d.target_temp),
                            borderColor: 'rgb(249, 115, 22)',
                            backgroundColor: 'rgba(249, 115, 22, 0.1)',
                            borderDash: [5, 5],
                            tension: 0.3,
                            fill: false,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'MMM d, HH:mm'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Temperature (°C)'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top'
                        }
                    }
                }
            });
        }

        // Daily Override Rate Chart
        if (dailyData.length > 0) {
            const overrideCtx = document.getElementById('overrideChart').getContext('2d');
            new Chart(overrideCtx, {
                type: 'bar',
                data: {
                    labels: dailyData.map(d => d.date),
                    datasets: [
                        {
                            label: 'Override Rate %',
                            data: dailyData.map(d => d.override_rate),
                            backgroundColor: 'rgba(147, 51, 234, 0.7)',
                            borderColor: 'rgb(147, 51, 234)',
                            borderWidth: 1,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Total Decisions',
                            data: dailyData.map(d => d.total),
                            type: 'line',
                            borderColor: 'rgb(59, 130, 246)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            yAxisID: 'y1',
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            type: 'linear',
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Override Rate (%)'
                            },
                            min: 0,
                            max: 100
                        },
                        y1: {
                            type: 'linear',
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Decisions'
                            },
                            grid: {
                                drawOnChartArea: false
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top'
                        }
                    }
                }
            });
        }

        // Hourly Override Chart
        const hourlyLabels = [];
        const hourlyOverrides = [];
        const hourlyTotals = [];
        for (let h = 0; h < 24; h++) {
            hourlyLabels.push(h + ':00');
            const data = hourlyData[h] || { overrides: 0, total: 0, override_rate: 0 };
            hourlyOverrides.push(data.override_rate);
            hourlyTotals.push(data.total);
        }

        const hourlyCtx = document.getElementById('hourlyChart').getContext('2d');
        new Chart(hourlyCtx, {
            type: 'bar',
            data: {
                labels: hourlyLabels,
                datasets: [
                    {
                        label: 'Override Rate %',
                        data: hourlyOverrides,
                        backgroundColor: hourlyOverrides.map(v => v > 50 ? 'rgba(249, 115, 22, 0.7)' : 'rgba(147, 51, 234, 0.7)'),
                        borderColor: hourlyOverrides.map(v => v > 50 ? 'rgb(249, 115, 22)' : 'rgb(147, 51, 234)'),
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Override Rate (%)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Hour of Day'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const total = hourlyTotals[context.dataIndex];
                                return `Total decisions: ${total}`;
                            }
                        }
                    }
                }
            }
        });
    </script>
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
        timeline_data = await logger.get_timeline_data(days=7)
        daily_data = await logger.get_daily_stats(days=7)
        hourly_data = await logger.get_hourly_stats()
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
        timeline_data = {"timeline": []}
        daily_data = {"daily_stats": []}
        hourly_data = {"hourly_stats": {}}

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
    html = html.replace("{{ now }}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Add chart data as JSON
    import json
    html = html.replace("{{ timeline_json }}", json.dumps(timeline_data.get("timeline", [])))
    html = html.replace("{{ daily_json }}", json.dumps(daily_data.get("daily_stats", [])))
    html = html.replace("{{ hourly_json }}", json.dumps(hourly_data.get("hourly_stats", {})))

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


@app.get("/api/timeline")
async def api_timeline(days: int = 7):
    """API endpoint for timeline data."""
    logger = DecisionLogger()
    return await logger.get_timeline_data(days=days)


@app.get("/api/daily")
async def api_daily(days: int = 7):
    """API endpoint for daily stats."""
    logger = DecisionLogger()
    return await logger.get_daily_stats(days=days)


@app.get("/api/hourly")
async def api_hourly():
    """API endpoint for hourly stats."""
    logger = DecisionLogger()
    return await logger.get_hourly_stats()
