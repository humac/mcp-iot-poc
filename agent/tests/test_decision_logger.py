"""
Tests for DecisionLogger database operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os


class TestDecisionLoggerInitialization:
    """Test DecisionLogger initialization."""
    
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self):
        """Test database tables are created on initialize."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Verify tables exist by trying to query them
            import aiosqlite
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in await cursor.fetchall()]
            
            assert "decisions" in tables
            assert "prompts" in tables
            assert "settings" in tables
            
            await logger.close()


class TestDecisionLoggerDecisions:
    """Test decision logging operations."""
    
    @pytest.mark.asyncio
    async def test_log_decision_basic(self):
        """Test basic decision logging."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            row_id = await logger.log_decision(
                action="SET_TEMPERATURE",
                reasoning="Test reasoning",
                ai_temperature=21.0,
            )
            
            assert row_id == 1
            await logger.close()
    
    @pytest.mark.asyncio
    async def test_log_decision_with_baseline(self):
        """Test decision logging with baseline comparison."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            baseline_decision = {
                "action": "SET_TEMPERATURE",
                "temperature": 20.0,
                "rule_triggered": "time_based",
                "reasoning": "Daytime schedule",
            }
            
            row_id = await logger.log_decision(
                action="SET_TEMPERATURE",
                reasoning="AI decided higher temp",
                ai_temperature=21.0,
                baseline_decision=baseline_decision,
            )
            
            # Verify stored correctly
            decisions = await logger.get_recent_decisions(limit=1)
            assert len(decisions) == 1
            assert decisions[0]["baseline_action"] == "SET_TEMPERATURE"
            assert decisions[0]["decisions_match"] == 0  # Different temps
            
            await logger.close()
    
    @pytest.mark.asyncio
    async def test_get_recent_decisions(self):
        """Test retrieving recent decisions."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Log multiple decisions
            for i in range(5):
                await logger.log_decision(
                    action=f"ACTION_{i}",
                    reasoning=f"Reason {i}",
                )
            
            # Get recent 3
            decisions = await logger.get_recent_decisions(limit=3)
            assert len(decisions) == 3
            # Should be in reverse order (most recent first)
            assert decisions[0]["action"] == "ACTION_4"
            
            await logger.close()


class TestDecisionLoggerStats:
    """Test statistics operations."""
    
    @pytest.mark.asyncio
    async def test_get_decision_stats(self):
        """Test decision statistics."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Log some decisions
            for _ in range(3):
                await logger.log_decision(action="SET_TEMPERATURE", reasoning="Test")
            for _ in range(2):
                await logger.log_decision(action="NO_CHANGE", reasoning="Test")
            
            stats = await logger.get_decision_stats()
            
            assert stats["total_decisions"] == 5
            assert stats["action_breakdown"]["SET_TEMPERATURE"] == 3
            assert stats["action_breakdown"]["NO_CHANGE"] == 2
            
            await logger.close()


class TestDecisionLoggerSettings:
    """Test settings management."""
    
    @pytest.mark.asyncio
    async def test_get_setting_creates_default(self):
        """Test getting a setting creates default if not exists."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            value = await logger.get_setting("new_setting", "default_value", "Description")
            assert value == "default_value"
            
            # Get again - should still return default
            value2 = await logger.get_setting("new_setting", "different_default", "Desc")
            assert value2 == "default_value"
            
            await logger.close()
    
    @pytest.mark.asyncio
    async def test_update_setting(self):
        """Test updating a setting."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Create setting
            await logger.get_setting("test_key", "original")
            
            # Update it
            await logger.update_setting("test_key", "updated")
            
            # Verify update
            value = await logger.get_setting("test_key", "default")
            assert value == "updated"
            
            await logger.close()

    @pytest.mark.asyncio
    async def test_update_setting_upsert(self):
        """Test updating a non-existent setting creates it (UPSERT)."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Update non-existent key
            await logger.update_setting("new_upsert_key", "upserted_value")
            
            # Verify it exists now
            value = await logger.get_setting("new_upsert_key", "default")
            assert value == "upserted_value"
            
            await logger.close()


class TestDecisionLoggerPrompts:
    """Test prompt management."""
    
    @pytest.mark.asyncio
    async def test_get_prompt_creates_default(self):
        """Test getting a prompt creates default if not exists."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            prompt = await logger.get_prompt("system_prompt", "You are a helpful assistant")
            assert prompt == "You are a helpful assistant"
            
            await logger.close()
    
    @pytest.mark.asyncio
    async def test_update_prompt(self):
        """Test updating a prompt."""
        from climate_agent.decision_logger import DecisionLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            logger = DecisionLogger(db_path)
            await logger.initialize()
            
            # Create prompt
            await logger.get_prompt("my_prompt", "original content")
            
            # Update it
            await logger.update_prompt("my_prompt", "new content")
            
            # Verify (need to check DB directly since get_prompt doesn't re-fetch)
            all_prompts = await logger.get_all_prompts()
            my_prompt = next(p for p in all_prompts if p["key"] == "my_prompt")
            assert my_prompt["content"] == "new content"
            
            await logger.close()
