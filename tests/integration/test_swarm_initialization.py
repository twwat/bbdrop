"""
Integration tests for swarm initialization workflow.
Tests complete swarm setup, agent spawning, and coordination.
"""

import pytest
import json
from datetime import datetime


@pytest.mark.integration
class TestSwarmInitializationWorkflow:
    """Test complete swarm initialization workflow."""

    def test_full_initialization_flow(self, temp_dir, sample_swarm_config,
                                       sample_agent_instructions, write_json_file):
        """Test complete initialization from config to agent spawning."""
        # Step 1: Write configuration
        config_path = write_json_file("swarm/config/swarm-init.json", sample_swarm_config)
        instructions_path = write_json_file("swarm/tasks/agent-instructions.json",
                                            sample_agent_instructions)

        # Step 2: Verify files exist
        assert config_path.exists()
        assert instructions_path.exists()

        # Step 3: Load and validate configuration
        with open(config_path) as f:
            loaded_config = json.load(f)

        assert loaded_config["swarmId"] == sample_swarm_config["swarmId"]
        assert loaded_config["topology"] == "mesh"

        # Step 4: Load agent instructions
        with open(instructions_path) as f:
            loaded_instructions = json.load(f)

        assert "researcher" in loaded_instructions
        assert "coder" in loaded_instructions

        # Step 5: Simulate agent spawning
        spawned_agents = []
        for agent_type, instructions in loaded_instructions.items():
            agent_record = {
                "agent_type": agent_type,
                "objective": instructions["objective"],
                "task_count": len(instructions["tasks"]),
                "status": "initialized"
            }
            spawned_agents.append(agent_record)

        # Verify all agents spawned
        assert len(spawned_agents) == len(sample_agent_instructions)
        assert all(agent["status"] == "initialized" for agent in spawned_agents)

    def test_initialization_with_memory_setup(self, temp_dir, temp_memory_db,
                                               sample_swarm_config, write_json_file):
        """Test initialization workflow includes memory setup."""
        # Write configuration
        write_json_file("swarm/config/swarm-init.json", sample_swarm_config)

        # Initialize memory with swarm config
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("swarm/config", json.dumps(sample_swarm_config), "system",
             int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Verify memory was initialized
        cursor = temp_memory_db.execute(
            "SELECT value FROM memory WHERE key = ? AND namespace = ?",
            ("swarm/config", "system")
        )
        row = cursor.fetchone()

        assert row is not None
        stored_config = json.loads(row[0])
        assert stored_config["swarmId"] == sample_swarm_config["swarmId"]

    def test_initialization_creates_directory_structure(self, temp_dir, mock_file_system):
        """Test initialization creates required directory structure."""
        # Verify directory structure was created
        required_dirs = [
            "swarm/config",
            "swarm/memory",
            "swarm/results",
            "swarm/tasks",
            "swarm/architecture",
            "swarm/docs"
        ]

        for dir_path in required_dirs:
            full_path = mock_file_system / dir_path
            assert full_path.exists(), f"Directory {dir_path} should exist"
            assert full_path.is_dir(), f"{dir_path} should be a directory"


@pytest.mark.integration
class TestAgentSpawningCoordination:
    """Test agent spawning and coordination setup."""

    def test_sequential_agent_spawning(self, temp_memory_db, sample_agent_instructions):
        """Test agents spawn in correct sequence."""
        # Define agent spawn order
        spawn_order = ["researcher", "system-architect", "planner", "code-analyzer", "tester"]

        spawned = []
        for agent_type in spawn_order:
            if agent_type in sample_agent_instructions:
                # Simulate agent spawn
                agent_id = f"agent-{len(spawned)+1}"
                agent_record = {
                    "agent_id": agent_id,
                    "type": agent_type,
                    "spawned_at": datetime.now().isoformat()
                }

                # Store in memory
                temp_memory_db.execute(
                    "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                    (f"swarm/agents/{agent_id}", json.dumps(agent_record), "coordination",
                     int(datetime.now().timestamp()))
                )
                spawned.append(agent_id)

        temp_memory_db.commit()

        # Verify agents were spawned
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ? AND key LIKE ?",
            ("coordination", "swarm/agents/%")
        )
        count = cursor.fetchone()[0]

        assert count == len(spawned)

    def test_parallel_agent_spawning(self, temp_memory_db, sample_agent_instructions):
        """Test multiple agents spawning in parallel."""
        import concurrent.futures
        import time

        def spawn_agent(agent_type, instructions, db_path):
            """Simulate spawning a single agent."""
            import sqlite3
            conn = sqlite3.connect(db_path)

            agent_id = f"agent-{agent_type}"
            agent_record = {
                "agent_id": agent_id,
                "type": agent_type,
                "objective": instructions["objective"],
                "spawned_at": datetime.now().isoformat()
            }

            conn.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"swarm/agents/{agent_id}", json.dumps(agent_record), "coordination",
                 int(datetime.now().timestamp()))
            )
            conn.commit()
            conn.close()

            time.sleep(0.1)  # Simulate spawn time
            return agent_id

        # Get database path
        cursor = temp_memory_db.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        # Spawn agents in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for agent_type, instructions in sample_agent_instructions.items():
                future = executor.submit(spawn_agent, agent_type, instructions, db_path)
                futures.append(future)

            # Wait for all to complete
            [f.result() for f in concurrent.futures.as_completed(futures)]

        # Verify all agents spawned
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ? AND key LIKE ?",
            ("coordination", "swarm/agents/%")
        )
        count = cursor.fetchone()[0]

        assert count == len(sample_agent_instructions)

    def test_agent_coordination_handshake(self, temp_memory_db):
        """Test agents coordinate via handshake protocol."""
        # Agent 1 registers
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("swarm/agents/agent-1/status", json.dumps({"status": "ready", "waiting_for": ["agent-2"]}),
             "coordination", int(datetime.now().timestamp()))
        )

        # Agent 2 registers
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("swarm/agents/agent-2/status", json.dumps({"status": "ready", "waiting_for": []}),
             "coordination", int(datetime.now().timestamp()))
        )

        temp_memory_db.commit()

        # Agent 1 checks Agent 2 status
        cursor = temp_memory_db.execute(
            "SELECT value FROM memory WHERE key = ? AND namespace = ?",
            ("swarm/agents/agent-2/status", "coordination")
        )
        row = cursor.fetchone()

        agent2_status = json.loads(row[0])
        assert agent2_status["status"] == "ready"

        # Agent 1 updates status (handshake complete)
        temp_memory_db.execute(
            "UPDATE memory SET value = ? WHERE key = ? AND namespace = ?",
            (json.dumps({"status": "ready", "waiting_for": []}),
             "swarm/agents/agent-1/status", "coordination")
        )
        temp_memory_db.commit()


@pytest.mark.integration
class TestMemoryPersistence:
    """Test memory persistence across operations."""

    def test_memory_persists_across_operations(self, temp_memory_db):
        """Test memory data persists across multiple operations."""
        # Write data
        test_data = {"counter": 0}
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("counter", json.dumps(test_data), "test", int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Perform multiple updates
        for i in range(1, 6):
            cursor = temp_memory_db.execute(
                "SELECT value FROM memory WHERE key = ? AND namespace = ?",
                ("counter", "test")
            )
            row = cursor.fetchone()
            data = json.loads(row[0])

            data["counter"] = i
            temp_memory_db.execute(
                "UPDATE memory SET value = ? WHERE key = ? AND namespace = ?",
                (json.dumps(data), "counter", "test")
            )
            temp_memory_db.commit()

        # Verify final value
        cursor = temp_memory_db.execute(
            "SELECT value FROM memory WHERE key = ? AND namespace = ?",
            ("counter", "test")
        )
        row = cursor.fetchone()
        final_data = json.loads(row[0])

        assert final_data["counter"] == 5

    def test_memory_transaction_consistency(self, temp_memory_db):
        """Test memory maintains consistency during transactions."""
        # Start transaction
        keys = ["key1", "key2", "key3"]

        try:
            for key in keys:
                temp_memory_db.execute(
                    "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                    (key, json.dumps({"value": key}), "transaction-test",
                     int(datetime.now().timestamp()))
                )

            temp_memory_db.commit()

        except Exception as e:
            temp_memory_db.rollback()
            raise e

        # Verify all keys were written
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ?",
            ("transaction-test",)
        )
        count = cursor.fetchone()[0]

        assert count == len(keys)

    def test_memory_rollback_on_error(self, temp_memory_db):
        """Test memory rolls back on error."""
        # Insert initial data
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("original", json.dumps({"value": "original"}), "rollback-test",
             int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Attempt transaction with error
        try:
            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                ("new-key", json.dumps({"value": "new"}), "rollback-test",
                 int(datetime.now().timestamp()))
            )

            # Force error with duplicate key
            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                ("original", json.dumps({"value": "duplicate"}), "rollback-test",
                 int(datetime.now().timestamp()))
            )

            temp_memory_db.commit()

        except Exception:
            temp_memory_db.rollback()

        # Verify only original data exists
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ?",
            ("rollback-test",)
        )
        count = cursor.fetchone()[0]

        assert count == 1  # Only original key should exist


@pytest.mark.integration
class TestHookIntegration:
    """Test hook integration with system components."""

    def test_hooks_coordinate_with_memory(self, temp_memory_db):
        """Test hooks store data in memory coordination system."""
        task_id = "integration-task-001"

        # Pre-task hook: Create task and store in memory
        temp_memory_db.execute(
            "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "Integration test task", "pending", int(datetime.now().timestamp()))
        )

        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            (f"hooks/pre-task/{task_id}", json.dumps({"hook": "pre-task", "task_id": task_id}),
             "hooks", int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Verify both task and hook data exist
        cursor = temp_memory_db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        task_row = cursor.fetchone()

        cursor = temp_memory_db.execute(
            "SELECT * FROM memory WHERE key = ? AND namespace = ?",
            (f"hooks/pre-task/{task_id}", "hooks")
        )
        hook_row = cursor.fetchone()

        assert task_row is not None
        assert hook_row is not None

    def test_hook_pipeline_with_coordination(self, temp_memory_db, coordination_log):
        """Test complete hook pipeline with coordination logging."""
        entries, log_func = coordination_log
        task_id = "pipeline-task"

        # Pre-task
        temp_memory_db.execute(
            "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "Pipeline test", "pending", int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()
        log_func("agent-1", "pre-task", {"task_id": task_id})

        # Work phase
        temp_memory_db.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            ("in-progress", task_id)
        )
        temp_memory_db.commit()
        log_func("agent-1", "work-progress", {"task_id": task_id, "progress": 0.5})

        # Post-task
        temp_memory_db.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
            ("completed", int(datetime.now().timestamp()), task_id)
        )
        temp_memory_db.commit()
        log_func("agent-1", "post-task", {"task_id": task_id, "status": "completed"})

        # Verify complete pipeline
        assert len(entries) == 3
        assert entries[0]["action"] == "pre-task"
        assert entries[1]["action"] == "work-progress"
        assert entries[2]["action"] == "post-task"

        # Verify task completed
        cursor = temp_memory_db.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (task_id,)
        )
        status = cursor.fetchone()[0]
        assert status == "completed"


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndInitialization:
    """End-to-end initialization tests."""

    def test_complete_initialization_scenario(self, temp_dir, temp_memory_db,
                                               sample_swarm_config, sample_agent_instructions,
                                               sample_objective, write_json_file):
        """Test complete initialization scenario from start to finish."""
        # Step 1: Setup - Write all configuration files
        config_path = write_json_file("swarm/config/swarm-init.json", sample_swarm_config)
        write_json_file("swarm/tasks/agent-instructions.json",
                                            sample_agent_instructions)
        write_json_file("swarm/memory/objective.json", sample_objective)

        # Step 2: Initialize swarm in memory
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("swarm/init", json.dumps(sample_swarm_config), "system",
             int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Step 3: Spawn agents
        spawned_agents = []
        for agent_type, instructions in sample_agent_instructions.items():
            agent_id = f"agent-{agent_type}"

            # Create agent record
            agent_record = {
                "agent_id": agent_id,
                "type": agent_type,
                "objective": instructions["objective"],
                "status": "initialized"
            }

            # Store in memory
            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"swarm/agents/{agent_id}", json.dumps(agent_record), "coordination",
                 int(datetime.now().timestamp()))
            )

            spawned_agents.append(agent_id)

        temp_memory_db.commit()

        # Step 4: Each agent runs pre-task hook
        for agent_id in spawned_agents:
            task_id = f"{agent_id}-task-001"

            temp_memory_db.execute(
                "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
                (task_id, f"Task for {agent_id}", "pending",
                 int(datetime.now().timestamp()))
            )

        temp_memory_db.commit()

        # Step 5: Verify complete system state
        # Check config exists
        assert config_path.exists()

        # Check swarm initialized in memory
        cursor = temp_memory_db.execute(
            "SELECT value FROM memory WHERE key = ? AND namespace = ?",
            ("swarm/init", "system")
        )
        swarm_data = json.loads(cursor.fetchone()[0])
        assert swarm_data["swarmId"] == sample_swarm_config["swarmId"]

        # Check all agents spawned
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ? AND key LIKE ?",
            ("coordination", "swarm/agents/%")
        )
        agent_count = cursor.fetchone()[0]
        assert agent_count == len(sample_agent_instructions)

        # Check all tasks created
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM tasks"
        )
        task_count = cursor.fetchone()[0]
        assert task_count == len(spawned_agents)

        # Step 6: Verify system is ready for work
        cursor = temp_memory_db.execute(
            "SELECT value FROM memory WHERE namespace = ? AND key LIKE ?",
            ("coordination", "swarm/agents/%")
        )

        all_agents_ready = True
        for row in cursor.fetchall():
            agent_data = json.loads(row[0])
            if agent_data["status"] != "initialized":
                all_agents_ready = False
                break

        assert all_agents_ready, "All agents should be initialized and ready"
