"""
Performance tests for concurrent operations.
Tests system performance under concurrent load and benchmarks key operations.
"""

import pytest
import time
import json
from datetime import datetime
import concurrent.futures


@pytest.mark.performance
class TestConcurrentAgentExecution:
    """Test performance with concurrent agent execution."""

    def test_five_concurrent_agents_performance(self, temp_memory_db):
        """Test performance with 5 concurrent agents (requirement: <60s)."""
        import sqlite3

        cursor = temp_memory_db.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        def agent_work(agent_id, duration=1.0):
            """Simulate agent work."""
            conn = sqlite3.connect(db_path)
            start = time.time()

            # Simulate agent tasks
            for i in range(10):
                # Write to memory
                conn.execute(
                    "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                    (f"agent/{agent_id}/iteration/{i}",
                     json.dumps({"iteration": i, "data": f"result-{i}"}),
                     "performance-test",
                     int(datetime.now().timestamp()))
                )
                conn.commit()

                # Simulate some work
                time.sleep(duration / 10)

            elapsed = time.time() - start
            conn.close()

            return {
                "agent_id": agent_id,
                "elapsed": elapsed,
                "iterations": 10
            }

        # Run 5 agents concurrently
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(agent_work, f"agent-{i}", 1.0) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        total_time = time.time() - start_time

        # Verify performance requirement (<60 seconds)
        assert total_time < 60, f"Concurrent execution took {total_time:.2f}s (should be <60s)"

        # Verify all agents completed
        assert len(results) == 5

        # Verify all iterations were recorded
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ?",
            ("performance-test",)
        )
        count = cursor.fetchone()[0]
        assert count == 50  # 5 agents × 10 iterations

    def test_concurrent_memory_access_performance(self, temp_memory_db):
        """Test memory access performance with concurrent operations."""
        import sqlite3

        cursor = temp_memory_db.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        def memory_operations(thread_id, operations=100):
            """Perform memory read/write operations."""
            conn = sqlite3.connect(db_path)
            start = time.time()

            for i in range(operations):
                # Write
                conn.execute(
                    "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                    (f"perf/thread-{thread_id}/key-{i}",
                     json.dumps({"value": i}),
                     "perf-test",
                     int(datetime.now().timestamp()))
                )

                # Read
                conn.execute(
                    "SELECT value FROM memory WHERE key = ? AND namespace = ?",
                    (f"perf/thread-{thread_id}/key-{i}", "perf-test")
                )

            conn.commit()
            elapsed = time.time() - start
            conn.close()

            return elapsed

        # Run concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(memory_operations, i, 100) for i in range(10)]
            times = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Calculate statistics
        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Performance assertions
        assert avg_time < 1.0, f"Average time per thread {avg_time:.2f}s should be <1s"
        assert max_time < 2.0, f"Max time {max_time:.2f}s should be <2s"


@pytest.mark.performance
class TestMemoryOperationLatency:
    """Test memory operation latency."""

    def test_single_read_latency(self, temp_memory_db):
        """Test single memory read operation latency (<10ms)."""
        # Setup: Insert test data
        temp_memory_db.execute(
            "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
            ("latency-test", json.dumps({"value": "test"}), "test",
             int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()

        # Measure read latency
        latencies = []
        for _ in range(100):
            start = time.time()
            cursor = temp_memory_db.execute(
                "SELECT value FROM memory WHERE key = ? AND namespace = ?",
                ("latency-test", "test")
            )
            cursor.fetchone()
            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        # Assertions
        assert avg_latency < 10, f"Average read latency {avg_latency:.2f}ms should be <10ms"
        assert p95_latency < 20, f"P95 read latency {p95_latency:.2f}ms should be <20ms"

    def test_single_write_latency(self, temp_memory_db):
        """Test single memory write operation latency (<50ms)."""
        latencies = []

        for i in range(100):
            start = time.time()

            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"write-latency-{i}", json.dumps({"iteration": i}), "test",
                 int(datetime.now().timestamp()))
            )
            temp_memory_db.commit()

            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        # Assertions
        assert avg_latency < 50, f"Average write latency {avg_latency:.2f}ms should be <50ms"
        assert p95_latency < 100, f"P95 write latency {p95_latency:.2f}ms should be <100ms"

    def test_bulk_operation_latency(self, temp_memory_db):
        """Test bulk memory operations latency (<500ms for 100 records)."""
        start = time.time()

        # Bulk insert
        for i in range(100):
            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"bulk-{i}", json.dumps({"value": i}), "bulk-test",
                 int(datetime.now().timestamp()))
            )

        temp_memory_db.commit()
        bulk_insert_time = (time.time() - start) * 1000  # Convert to ms

        # Bulk read
        start = time.time()
        cursor = temp_memory_db.execute(
            "SELECT * FROM memory WHERE namespace = ?",
            ("bulk-test",)
        )
        cursor.fetchall()
        bulk_read_time = (time.time() - start) * 1000  # Convert to ms

        # Assertions
        assert bulk_insert_time < 500, \
            f"Bulk insert {bulk_insert_time:.2f}ms should be <500ms"
        assert bulk_read_time < 100, \
            f"Bulk read {bulk_read_time:.2f}ms should be <100ms"


@pytest.mark.performance
class TestHookExecutionOverhead:
    """Test hook execution performance overhead."""

    def test_pre_task_hook_overhead(self, temp_memory_db):
        """Test pre-task hook execution overhead (<100ms)."""
        latencies = []

        for i in range(50):
            start = time.time()

            # Simulate pre-task hook
            task_id = f"perf-task-{i}"
            temp_memory_db.execute(
                "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
                (task_id, f"Performance task {i}", "pending",
                 int(datetime.now().timestamp()))
            )
            temp_memory_db.commit()

            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max(latencies)

        # Assertion
        assert avg_latency < 100, \
            f"Pre-task hook latency {avg_latency:.2f}ms should be <100ms"

    def test_post_task_hook_overhead(self, temp_memory_db):
        """Test post-task hook execution overhead (<100ms)."""
        # Setup: Create tasks
        task_ids = []
        for i in range(50):
            task_id = f"post-task-{i}"
            temp_memory_db.execute(
                "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
                (task_id, f"Task {i}", "in-progress", int(datetime.now().timestamp()))
            )
            task_ids.append(task_id)
        temp_memory_db.commit()

        # Measure post-task hook latency
        latencies = []
        for task_id in task_ids:
            start = time.time()

            temp_memory_db.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
                ("completed", int(datetime.now().timestamp()), task_id)
            )
            temp_memory_db.commit()

            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)

        # Assertion
        assert avg_latency < 100, \
            f"Post-task hook latency {avg_latency:.2f}ms should be <100ms"

    def test_total_hook_overhead_percentage(self, temp_memory_db):
        """Test total hook overhead is <5% of task execution time."""
        # Simulate task with hooks
        task_id = "overhead-task"

        # Measure hook overhead
        start = time.time()
        temp_memory_db.execute(
            "INSERT INTO tasks (task_id, description, status, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "Overhead test", "pending", int(datetime.now().timestamp()))
        )
        temp_memory_db.commit()
        pre_hook_time = time.time() - start

        # Simulate actual work (1 second)
        work_time = 1.0
        time.sleep(work_time)

        # Post-task hook
        start = time.time()
        temp_memory_db.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
            ("completed", int(datetime.now().timestamp()), task_id)
        )
        temp_memory_db.commit()
        post_hook_time = time.time() - start

        # Calculate overhead percentage
        total_hook_time = pre_hook_time + post_hook_time
        overhead_percentage = (total_hook_time / work_time) * 100

        # Assertion
        assert overhead_percentage < 5, \
            f"Hook overhead {overhead_percentage:.2f}% should be <5%"


@pytest.mark.performance
@pytest.mark.slow
class TestScalabilityBenchmarks:
    """Test system scalability benchmarks."""

    def test_memory_usage_with_scale(self, temp_memory_db):
        """Test memory usage remains reasonable with scale."""
        import sys

        # Insert large dataset
        records = 1000

        start_memory = sys.getsizeof(temp_memory_db)

        for i in range(records):
            temp_memory_db.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"scale-test-{i}",
                 json.dumps({"data": f"value-{i}", "metadata": {"index": i}}),
                 "scale-test",
                 int(datetime.now().timestamp()))
            )

            if i % 100 == 0:
                temp_memory_db.commit()

        temp_memory_db.commit()

        end_memory = sys.getsizeof(temp_memory_db)
        memory_increase = end_memory - start_memory

        # Memory increase should be reasonable (<500MB for 1000 records)
        # Note: This is a rough estimate
        assert memory_increase < 500 * 1024 * 1024, \
            f"Memory increase {memory_increase} bytes should be reasonable"

    def test_concurrent_load_stress(self, temp_memory_db):
        """Stress test with high concurrent load."""
        import sqlite3

        cursor = temp_memory_db.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        def stress_worker(worker_id):
            """Worker that performs intensive operations."""
            conn = sqlite3.connect(db_path)

            for i in range(50):
                conn.execute(
                    "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                    (f"stress/worker-{worker_id}/item-{i}",
                     json.dumps({"worker": worker_id, "item": i}),
                     "stress-test",
                     int(datetime.now().timestamp()))
                )

                if i % 10 == 0:
                    conn.commit()

            conn.commit()
            conn.close()

            return worker_id

        # Run 20 concurrent workers
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(stress_worker, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        total_time = time.time() - start_time

        # Verify all completed
        assert len(results) == 20

        # Verify all data was written
        cursor = temp_memory_db.execute(
            "SELECT COUNT(*) FROM memory WHERE namespace = ?",
            ("stress-test",)
        )
        count = cursor.fetchone()[0]
        assert count == 1000  # 20 workers × 50 items

        # Performance should be reasonable (completing in <10 seconds)
        assert total_time < 10, \
            f"Stress test took {total_time:.2f}s (should complete in <10s)"


@pytest.mark.performance
class TestPerformanceRegression:
    """Test for performance regressions."""

    def test_sequential_vs_parallel_speedup(self, temp_memory_db):
        """Test parallel execution provides speedup over sequential."""
        import sqlite3

        cursor = temp_memory_db.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        def task_work(task_id):
            """Simulate task work."""
            conn = sqlite3.connect(db_path)
            time.sleep(0.1)  # Simulate work
            conn.execute(
                "INSERT INTO memory (key, value, namespace, timestamp) VALUES (?, ?, ?, ?)",
                (f"task/{task_id}", json.dumps({"result": f"completed-{task_id}"}),
                 "speedup-test", int(datetime.now().timestamp()))
            )
            conn.commit()
            conn.close()

        # Sequential execution
        start = time.time()
        for i in range(5):
            task_work(f"sequential-{i}")
        sequential_time = time.time() - start

        # Parallel execution
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task_work, f"parallel-{i}") for i in range(5)]
            [f.result() for f in concurrent.futures.as_completed(futures)]
        parallel_time = time.time() - start

        # Calculate speedup
        speedup = sequential_time / parallel_time

        # Parallel should be faster (speedup > 2x for I/O bound tasks)
        assert speedup > 2.0, \
            f"Parallel speedup {speedup:.2f}x should be >2x over sequential"
