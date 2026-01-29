"""
Decision Logger

Persists agent decisions to SQLite for dashboard display and analysis.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/app/data/decisions.db")


class DecisionLogger:
    """Logs agent decisions to SQLite database."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create persistent database connection."""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
        return self._connection
    
    async def close(self):
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def initialize(self):
        """Create database tables if they don't exist."""
        db = await self._get_connection()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                weather_data TEXT,
                thermostat_state TEXT,
                action TEXT NOT NULL,
                ai_temperature REAL,
                reasoning TEXT,
                tool_calls TEXT,
                baseline_action TEXT,
                baseline_temperature REAL,
                baseline_rule TEXT,
                baseline_reasoning TEXT,
                decisions_match INTEGER,
                success INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                key TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                description TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                category TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT,
                details TEXT,
                blocked INTEGER DEFAULT 1
            )
        """)
        await db.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    async def log_decision(
        self,
        action: str,
        reasoning: str,
        weather_data: dict = None,
        thermostat_state: dict = None,
        tool_calls: list = None,
        baseline_decision: dict = None,
        ai_temperature: float = None,
        success: bool = True,
    ) -> int:
        """Log a decision to the database with baseline comparison."""
        
        # Extract baseline data
        baseline_action = None
        baseline_temperature = None
        baseline_rule = None
        baseline_reasoning = None
        decisions_match = None
        
        if baseline_decision:
            baseline_action = baseline_decision.get("action")
            baseline_temperature = baseline_decision.get("temperature")
            baseline_rule = baseline_decision.get("rule_triggered")
            baseline_reasoning = baseline_decision.get("reasoning")
            
            # Check if decisions match
            if action == "NO_CHANGE" and baseline_action == "NO_CHANGE":
                decisions_match = 1
            elif action == baseline_action and ai_temperature == baseline_temperature:
                decisions_match = 1
            else:
                decisions_match = 0
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO decisions 
                (timestamp, weather_data, thermostat_state, action, ai_temperature,
                 reasoning, tool_calls, baseline_action, baseline_temperature,
                 baseline_rule, baseline_reasoning, decisions_match, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),  # Use local time (respects TZ env var)
                    json.dumps(weather_data) if weather_data else None,
                    json.dumps(thermostat_state) if thermostat_state else None,
                    action,
                    ai_temperature,
                    reasoning,
                    json.dumps(tool_calls) if tool_calls else None,
                    baseline_action,
                    baseline_temperature,
                    baseline_rule,
                    baseline_reasoning,
                    decisions_match,
                    1 if success else 0,
                ),
            )
            await db.commit()
            
            if decisions_match == 0:
                logger.info(f"Logged DIFFERENT decision: AI={action} vs Baseline={baseline_action}")
            else:
                logger.info(f"Logged decision: {action}")
            
            return cursor.lastrowid
    
    async def get_recent_decisions(self, limit: int = 20) -> list[dict]:
        """Get recent decisions from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM decisions 
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                # Parse JSON fields
                if decision.get("weather_data"):
                    decision["weather_data"] = json.loads(decision["weather_data"])
                if decision.get("thermostat_state"):
                    decision["thermostat_state"] = json.loads(decision["thermostat_state"])
                if decision.get("tool_calls"):
                    decision["tool_calls"] = json.loads(decision["tool_calls"])
                decisions.append(decision)
            
            return decisions
    
    async def get_comparison_stats(self) -> dict[str, Any]:
        """Get statistics comparing AI vs baseline decisions."""
        async with aiosqlite.connect(self.db_path) as db:
            # Total decisions with comparison data
            cursor = await db.execute(
                "SELECT COUNT(*) FROM decisions WHERE baseline_action IS NOT NULL"
            )
            total_compared = (await cursor.fetchone())[0]
            
            # Matching decisions
            cursor = await db.execute(
                "SELECT COUNT(*) FROM decisions WHERE decisions_match = 1"
            )
            matching = (await cursor.fetchone())[0]
            
            # Different decisions
            cursor = await db.execute(
                "SELECT COUNT(*) FROM decisions WHERE decisions_match = 0"
            )
            different = (await cursor.fetchone())[0]
            
            # Get examples of different decisions
            cursor = await db.execute(
                """
                SELECT timestamp, action, ai_temperature, baseline_action, 
                       baseline_temperature, baseline_rule, reasoning
                FROM decisions 
                WHERE decisions_match = 0
                ORDER BY timestamp DESC
                LIMIT 5
                """
            )
            different_examples = []
            for row in await cursor.fetchall():
                different_examples.append({
                    "timestamp": row[0],
                    "ai_action": row[1],
                    "ai_temp": row[2],
                    "baseline_action": row[3],
                    "baseline_temp": row[4],
                    "baseline_rule": row[5],
                    "ai_reasoning": row[6][:200] if row[6] else None,
                })
            
            return {
                "total_compared": total_compared,
                "matching_decisions": matching,
                "different_decisions": different,
                "ai_override_rate": round((different / total_compared * 100), 1) if total_compared > 0 else 0,
                "recent_differences": different_examples,
            }
    
    async def get_decision_stats(self) -> dict[str, Any]:
        """Get statistics about decisions."""
        async with aiosqlite.connect(self.db_path) as db:
            # Total decisions
            cursor = await db.execute("SELECT COUNT(*) FROM decisions")
            total = (await cursor.fetchone())[0]
            
            # Decisions today
            today = datetime.now().date().isoformat()  # Use local time
            cursor = await db.execute(
                "SELECT COUNT(*) FROM decisions WHERE timestamp LIKE ?",
                (f"{today}%",),
            )
            today_count = (await cursor.fetchone())[0]
            
            # Action breakdown
            cursor = await db.execute(
                """
                SELECT action, COUNT(*) as count 
                FROM decisions 
                GROUP BY action 
                ORDER BY count DESC
                """
            )
            actions = await cursor.fetchall()
            
            # Success rate
            cursor = await db.execute(
                "SELECT AVG(success) * 100 FROM decisions"
            )
            success_rate = (await cursor.fetchone())[0] or 100
            
            return {
                "total_decisions": total,
                "decisions_today": today_count,
                "action_breakdown": {row[0]: row[1] for row in actions},
                "success_rate": round(success_rate, 1),
            }

    async def get_timeline_data(self, days: int = 7) -> dict[str, Any]:
        """Get decision timeline data for charting."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get all decisions with temperature data for the time period
            cursor = await db.execute(
                """
                SELECT
                    timestamp,
                    action,
                    ai_temperature,
                    baseline_action,
                    baseline_temperature,
                    decisions_match,
                    weather_data,
                    thermostat_state
                FROM decisions
                WHERE timestamp >= datetime('now', ?)
                ORDER BY timestamp ASC
                """,
                (f'-{days} days',),
            )
            rows = await cursor.fetchall()

            timeline = []
            for row in rows:
                weather = json.loads(row[6]) if row[6] else {}
                thermostat = json.loads(row[7]) if row[7] else {}
                
                # Filter out bad data (e.g. Fahrenheit values > 50°C)
                indoor_temp = thermostat.get("current_temperature")
                if isinstance(indoor_temp, (int, float)) and indoor_temp > 50:
                    continue  # Skip this bad data point
                
                outdoor_temp = weather.get("temperature_c")
                if isinstance(outdoor_temp, (int, float)) and outdoor_temp > 50:
                    continue

                timeline.append({
                    "timestamp": row[0],
                    "action": row[1],
                    "ai_temperature": row[2],
                    "baseline_action": row[3],
                    "baseline_temperature": row[4],
                    "decisions_match": row[5],
                    "outdoor_temp": outdoor_temp,
                    "indoor_temp": indoor_temp,
                    "target_temp": thermostat.get("target_temperature"),
                })

            return {"timeline": timeline, "days": days}

    async def get_hourly_stats(self) -> dict[str, Any]:
        """Get decision breakdown by hour of day."""
        async with aiosqlite.connect(self.db_path) as db:
            # Decisions by hour
            cursor = await db.execute(
                """
                SELECT
                    CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN decisions_match = 0 THEN 1 ELSE 0 END) as overrides
                FROM decisions
                WHERE baseline_action IS NOT NULL
                GROUP BY hour
                ORDER BY hour
                """
            )
            rows = await cursor.fetchall()

            hourly = {}
            for row in rows:
                hourly[row[0]] = {
                    "total": row[1],
                    "overrides": row[2],
                    "override_rate": round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0
                }

            return {"hourly_stats": hourly}

    async def get_daily_stats(self, days: int = 7) -> dict[str, Any]:
        """Get daily decision statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT
                    DATE(timestamp) as date,
                    COUNT(*) as total,
                    SUM(CASE WHEN decisions_match = 0 THEN 1 ELSE 0 END) as overrides,
                    SUM(CASE WHEN action = 'SET_TEMPERATURE' THEN 1 ELSE 0 END) as temp_changes,
                    AVG(CASE WHEN ai_temperature IS NOT NULL THEN ai_temperature END) as avg_ai_temp
                FROM decisions
                WHERE timestamp >= datetime('now', ?)
                GROUP BY DATE(timestamp)
                ORDER BY date ASC
                """,
                (f'-{days} days',),
            )
            rows = await cursor.fetchall()

            daily = []
            for row in rows:
                daily.append({
                    "date": row[0],
                    "total": row[1],
                    "overrides": row[2],
                    "override_rate": round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0,
                    "temp_changes": row[3],
                    "avg_ai_temp": round(row[4], 1) if row[4] else None,
                })

            return {"daily_stats": daily, "days": days}

    async def get_prompt(self, key: str, default: str, description: str = "") -> str:
        """Get a prompt by key, creating it if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT content FROM prompts WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            
            if row:
                return row[0]
            
            # Create default if not exists
            now = datetime.now().isoformat()
            await db.execute(
                "INSERT INTO prompts (key, content, description, updated_at) VALUES (?, ?, ?, ?)",
                (key, default, description, now)
            )
            await db.commit()
            return default
            
    async def update_prompt(self, key: str, content: str) -> bool:
        """Update a prompt."""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now().isoformat()
            await db.execute(
                "UPDATE prompts SET content = ?, updated_at = ? WHERE key = ?",
                (content, now, key)
            )
            await db.commit()
            return True

    async def get_all_prompts(self) -> list[dict]:
        """Get all prompts."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM prompts ORDER BY key")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_setting(self, key: str, default: str, description: str = "", category: str = "General") -> str:
        """Get a setting by key, creating it if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            
            if row:
                return row[0]
            
            # Create default if not exists
            now = datetime.now().isoformat()
            await db.execute(
                "INSERT INTO settings (key, value, description, category, updated_at) VALUES (?, ?, ?, ?, ?)",
                (key, str(default), description, category, now)
            )
            await db.commit()
            return str(default)

    async def update_setting(self, key: str, value: str, description: str = "", category: str = "General") -> bool:
        """Update a setting, creating it if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now().isoformat()
            # Try update first
            cursor = await db.execute(
                "UPDATE settings SET value = ?, updated_at = ? WHERE key = ?",
                (str(value), now, key)
            )
            if cursor.rowcount == 0:
                # Insert if not exists
                await db.execute(
                    "INSERT INTO settings (key, value, description, category, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (key, str(value), description, category, now)
                )
            await db.commit()
            return True

    async def get_all_settings(self) -> list[dict]:
        """Get all settings."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM settings ORDER BY category, key")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def log_security_event(
        self,
        event_type: str,
        source: str,
        details: dict = None,
        blocked: bool = True
    ) -> int:
        """Log a security event to the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO security_events (timestamp, event_type, source, details, blocked)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    event_type,
                    source,
                    json.dumps(details) if details else None,
                    1 if blocked else 0,
                ),
            )
            await db.commit()
            logger.info(f"Logged security event: {event_type} from {source}")
            return cursor.lastrowid

    async def get_security_stats(self) -> dict[str, Any]:
        """Get security event statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            # Total events
            cursor = await db.execute("SELECT COUNT(*) FROM security_events")
            total = (await cursor.fetchone())[0]

            # Blocked actions
            cursor = await db.execute(
                "SELECT COUNT(*) FROM security_events WHERE event_type = 'blocked_action'"
            )
            blocked_actions = (await cursor.fetchone())[0]

            # Validation failures
            cursor = await db.execute(
                "SELECT COUNT(*) FROM security_events WHERE event_type = 'validation_failure'"
            )
            validation_failures = (await cursor.fetchone())[0]

            # Auth failures
            cursor = await db.execute(
                "SELECT COUNT(*) FROM security_events WHERE event_type = 'auth_failure'"
            )
            auth_failures = (await cursor.fetchone())[0]

            # Injection tests
            cursor = await db.execute(
                "SELECT COUNT(*) FROM security_events WHERE event_type = 'injection_test'"
            )
            injection_tests = (await cursor.fetchone())[0]

            # Recent events
            cursor = await db.execute(
                """
                SELECT timestamp, event_type, source, details, blocked
                FROM security_events
                ORDER BY timestamp DESC
                LIMIT 10
                """
            )
            recent = []
            for row in await cursor.fetchall():
                recent.append({
                    "timestamp": row[0],
                    "event_type": row[1],
                    "source": row[2],
                    "details": json.loads(row[3]) if row[3] else None,
                    "blocked": bool(row[4]),
                })

            return {
                "total_events": total,
                "blocked_actions": blocked_actions,
                "validation_failures": validation_failures,
                "auth_failures": auth_failures,
                "injection_tests": injection_tests,
                "recent_events": recent,
            }
