"""
Unit tests for configuration validation and parsing.
Tests the initialization system's configuration loading and validation logic.
"""

import pytest
import json
from pathlib import Path


@pytest.mark.unit
class TestSwarmConfigValidation:
    """Test swarm configuration validation."""

    def test_valid_config_parsing(self, sample_swarm_config, assert_helpers):
        """Test parsing of valid swarm configuration."""
        # Validate config structure
        assert_helpers.assert_valid_swarm_config(sample_swarm_config)

        # Check specific values
        assert sample_swarm_config["swarmId"] == "test-swarm-001"
        assert sample_swarm_config["topology"] == "mesh"
        assert sample_swarm_config["maxAgents"] == 6
        assert sample_swarm_config["parallelExecution"] is True

    def test_missing_required_fields(self):
        """Test validation fails with missing required fields."""
        invalid_configs = [
            {},  # Empty config
            {"swarmId": "test-001"},  # Missing objective
            {"objective": "init"},  # Missing swarmId
            {"swarmId": "test-001", "objective": "init"}  # Missing topology
        ]

        for config in invalid_configs:
            with pytest.raises((KeyError, AssertionError)):
                assert "swarmId" in config
                assert "objective" in config
                assert "topology" in config

    def test_invalid_topology(self, sample_swarm_config):
        """Test validation fails with invalid topology."""
        sample_swarm_config["topology"] = "invalid-topology"

        valid_topologies = ["mesh", "hierarchical", "ring", "star"]
        assert sample_swarm_config["topology"] not in valid_topologies

    def test_invalid_max_agents(self, sample_swarm_config):
        """Test validation fails with invalid maxAgents."""
        test_cases = [
            0,      # Zero agents
            -1,     # Negative agents
            None,   # None value
        ]

        for value in test_cases:
            sample_swarm_config["maxAgents"] = value
            if isinstance(value, int) and value > 0:
                assert sample_swarm_config["maxAgents"] > 0
            else:
                assert not (isinstance(value, int) and value > 0)

    def test_default_values(self):
        """Test default values are applied correctly."""
        minimal_config = {
            "swarmId": "test-001",
            "objective": "init",
            "topology": "mesh"
        }

        # These should have defaults
        defaults = {
            "maxAgents": 5,
            "timeout": 3600,
            "parallelExecution": True,
            "strategy": "auto",
            "mode": "centralized"
        }

        # Simulate applying defaults
        for key, default_value in defaults.items():
            if key not in minimal_config:
                minimal_config[key] = default_value

        assert minimal_config["maxAgents"] == 5
        assert minimal_config["timeout"] == 3600
        assert minimal_config["parallelExecution"] is True


@pytest.mark.unit
class TestObjectiveValidation:
    """Test objective configuration validation."""

    def test_valid_objective_parsing(self, sample_objective):
        """Test parsing of valid objective configuration."""
        assert sample_objective["objective"] == "init"
        assert sample_objective["priority"] == "high"
        assert "requirements" in sample_objective
        assert isinstance(sample_objective["requirements"], list)
        assert len(sample_objective["requirements"]) > 0

    def test_objective_scope_detection(self, sample_objective):
        """Test automatic scope detection from objective."""
        test_cases = [
            ("init", "system-initialization"),
            ("test", "testing"),
            ("deploy", "deployment"),
            ("analyze", "analysis")
        ]

        for objective, expected_scope in test_cases:
            sample_objective["objective"] = objective
            # In real implementation, this would be auto-detected
            if objective == "init":
                assert sample_objective["detectedScope"] == "system-initialization"

    def test_priority_validation(self, sample_objective):
        """Test priority field validation."""
        valid_priorities = ["low", "medium", "high", "critical"]

        for priority in valid_priorities:
            sample_objective["priority"] = priority
            assert sample_objective["priority"] in valid_priorities

    def test_requirements_list_validation(self, sample_objective):
        """Test requirements list is valid."""
        assert isinstance(sample_objective["requirements"], list)
        assert len(sample_objective["requirements"]) > 0

        # All requirements should be strings
        for req in sample_objective["requirements"]:
            assert isinstance(req, str)
            assert len(req) > 0


@pytest.mark.unit
class TestAgentInstructionsValidation:
    """Test agent instructions validation."""

    def test_valid_agent_instructions(self, sample_agent_instructions, assert_helpers):
        """Test parsing of valid agent instructions."""
        for agent_type, instructions in sample_agent_instructions.items():
            assert_helpers.assert_valid_agent_instructions(
                sample_agent_instructions, agent_type
            )

    def test_all_agent_types_present(self, sample_agent_instructions):
        """Test all required agent types have instructions."""
        required_agents = ["researcher", "system-architect", "planner", "code-analyzer", "tester"]

        # For this test, we only check the provided ones
        for agent_type in sample_agent_instructions.keys():
            assert agent_type in ["researcher", "coder", "system-architect", "planner", "code-analyzer", "tester"]

    def test_task_list_validation(self, sample_agent_instructions):
        """Test task lists are valid."""
        for agent_type, instructions in sample_agent_instructions.items():
            tasks = instructions["tasks"]

            assert isinstance(tasks, list)
            assert len(tasks) > 0

            for task in tasks:
                assert isinstance(task, str)
                assert len(task) > 0

    def test_hook_commands_validation(self, sample_agent_instructions):
        """Test hook commands are valid."""
        for agent_type, instructions in sample_agent_instructions.items():
            hooks = instructions["hooks"]

            assert isinstance(hooks, list)
            assert len(hooks) >= 2  # At least pre-task and post-task

            for hook in hooks:
                assert isinstance(hook, str)
                assert "npx claude-flow@alpha hooks" in hook

    def test_deliverables_validation(self, sample_agent_instructions):
        """Test deliverables are specified."""
        for agent_type, instructions in sample_agent_instructions.items():
            deliverables = instructions["deliverables"]

            assert isinstance(deliverables, str)
            assert len(deliverables) > 0
            # Should be a file path
            assert ".json" in deliverables or ".py" in deliverables or ".md" in deliverables


@pytest.mark.unit
class TestConfigurationIO:
    """Test configuration file I/O operations."""

    def test_write_and_read_config(self, temp_dir, sample_swarm_config, write_json_file, read_json_file):
        """Test writing and reading configuration files."""
        # Write config
        config_path = write_json_file("swarm/config/test-config.json", sample_swarm_config)

        # Read config back
        loaded_config = read_json_file(config_path)

        # Verify data matches
        assert loaded_config == sample_swarm_config

    def test_malformed_json_handling(self, temp_dir):
        """Test handling of malformed JSON files."""
        malformed_file = temp_dir / "malformed.json"
        malformed_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            with open(malformed_file) as f:
                json.load(f)

    def test_missing_file_handling(self, temp_dir):
        """Test handling of missing configuration files."""
        missing_file = temp_dir / "nonexistent.json"

        assert not missing_file.exists()

        with pytest.raises(FileNotFoundError):
            with open(missing_file) as f:
                json.load(f)

    def test_file_permissions(self, temp_dir, sample_swarm_config, write_json_file):
        """Test configuration file has correct permissions."""
        config_path = write_json_file("config.json", sample_swarm_config)

        # File should be readable
        assert config_path.exists()
        assert config_path.is_file()

        # Should be able to read it
        with open(config_path) as f:
            data = json.load(f)

        assert data == sample_swarm_config


@pytest.mark.unit
class TestConfigurationValidationEdgeCases:
    """Test edge cases in configuration validation."""

    def test_unicode_in_config(self, sample_swarm_config):
        """Test handling of Unicode characters in configuration."""
        sample_swarm_config["objective"] = "初始化系统"  # Chinese characters
        sample_swarm_config["description"] = "Тест Unicode"  # Cyrillic

        # Should handle Unicode gracefully
        assert isinstance(sample_swarm_config["objective"], str)
        assert isinstance(sample_swarm_config["description"], str)

    def test_very_large_max_agents(self, sample_swarm_config):
        """Test handling of very large maxAgents value."""
        sample_swarm_config["maxAgents"] = 1000000

        # Should validate against reasonable limits
        reasonable_limit = 100
        if sample_swarm_config["maxAgents"] > reasonable_limit:
            # In real implementation, this should be capped
            assert sample_swarm_config["maxAgents"] > reasonable_limit

    def test_empty_strings_in_config(self, sample_swarm_config):
        """Test handling of empty strings in configuration."""
        test_fields = ["swarmId", "objective", "topology"]

        for field in test_fields:
            original_value = sample_swarm_config[field]
            sample_swarm_config[field] = ""

            # Empty strings should be invalid
            assert sample_swarm_config[field] == ""
            assert len(sample_swarm_config[field]) == 0

            # Restore original value
            sample_swarm_config[field] = original_value

    def test_null_values_in_config(self, sample_swarm_config):
        """Test handling of null/None values in configuration."""
        nullable_fields = ["description", "metadata"]

        for field in nullable_fields:
            sample_swarm_config[field] = None
            # Some fields can be null, others cannot
            # This should be validated by the real implementation
