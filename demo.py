"""
Multiprocessing demo for the Python core dump system.
This demonstrates how core dumps work across multiple processes.
"""

import multiprocessing as mp
import os
import time

import torch

from dpdb import install_global_handler, uninstall_global_handler


def deep_function_call(depth, data, worker_id):
    if depth > 0:
        return deep_function_call(depth - 1, data, worker_id)
    else:
        # Simulate some work
        local_data = []
        for i in range(10):
            value = data[i % len(data)]
            result = 100 / value  # Will crash if value is 0
            local_data.append(result)
            print(f"Worker {worker_id}: processed {value} -> {result}")
            time.sleep(0.1)


def worker_task_1(worker_id, shared_data):
    """Worker that processes data and may crash with a deep function call."""
    print(f"Worker {worker_id} starting (PID: {os.getpid()})")

    local_data = deep_function_call(3, shared_data, worker_id)

    print(f"Worker {worker_id} completed successfully")
    return local_data


def worker_task_2(worker_id, items_to_process):
    """Worker that processes a pytorch tensor."""
    print(f"Worker {worker_id} starting (PID: {os.getpid()})")

    tensor = torch.tensor(items_to_process)
    results = tensor.sum()
    raise RuntimeError("This is a test error")

    return results


def memory_intensive_worker(worker_id, size_mb):
    """Worker that creates large data structures and may crash."""
    print(f"Worker {worker_id} starting (PID: {os.getpid()})")

    # Create increasingly large data structures
    data_structures = []
    for i in range(size_mb):
        # Create a large list (approximately 1MB)
        large_list = list(range(250000))  # ~1MB of integers
        data_structures.append(large_list)

        # Simulate some processing
        total = sum(large_list[:1000])
        average = total / len(large_list[:1000])

        print(f"Worker {worker_id}: Created structure {i+1}/{size_mb}, avg: {average}")

        # Simulate a crash condition
        if i == 2:
            # Force a crash by accessing invalid memory pattern
            _ = large_list[len(large_list)]  # IndexError

        time.sleep(0.2)

    return len(data_structures)


def run_multiprocessing_demo():
    """Run the multiprocessing demo with automatic core dump handling."""
    print("=== Multiprocessing Core Dump Demo ===")
    print(f"Main process PID: {os.getpid()}")

    # Create shared data that will cause different types of crashes
    crash_data = [5, 3, 0, 7, 2]  # 0 will cause division by zero
    index_data = [10, 20, 30]  # Too short for worker_task_2

    processes = []

    # Start workers using standard multiprocessing - all automatically get core dump handling!
    print("\nStarting workers with standard multiprocessing...")

    # Worker 1: Division by zero with deep call stack
    p1 = mp.Process(target=worker_task_1, args=(1, crash_data), name="Worker-1")
    processes.append(p1)
    p1.start()

    # Worker 2: Index error
    p2 = mp.Process(target=worker_task_2, args=(2, index_data), name="Worker-2")
    processes.append(p2)
    p2.start()

    # Worker 4: Memory intensive with crash
    p4 = mp.Process(target=memory_intensive_worker, args=(4, 5), name="Worker-4")
    processes.append(p4)
    p4.start()

    # Worker 5: Successful worker (no crash)
    safe_data = [1, 2, 3, 4, 5]  # No zeros
    p5 = mp.Process(target=worker_task_1, args=(5, safe_data), name="Worker-5")
    processes.append(p5)
    p5.start()

    # Wait for all processes to complete
    print("\nWaiting for workers to complete...")
    results = []

    for i, process in enumerate(processes):
        process.join()
        exit_code = process.exitcode

        if exit_code == 0:
            print(f"Worker {i+1}: Completed successfully")
        else:
            print(f"Worker {i+1}: Crashed with exit code {exit_code}")

        results.append(exit_code)

    return results


if __name__ == "__main__":
    # Set multiprocessing start method (important for Windows)
    mp.set_start_method("spawn", force=True)

    print("Python Multiprocessing Core Dump Demo")
    print("=" * 60)

    # Install the global handler
    install_global_handler()

    # Run the demo
    results = run_multiprocessing_demo()
    time.sleep(1)  # Wait for file operations

    # Check for core dump files
    import glob

    dump_files = glob.glob("*crash.pkl")

    print("\n" + "=" * 60)
    print("DEMO COMPLETE!")
    print(f"Results: {results}")
    print("Exit codes: 0=success, 1=error, negative=signal termination")

    if dump_files:
        print("\n🎯 Automatic core dumps created:")
        for dump_file in sorted(dump_files):
            file_size = os.path.getsize(dump_file)
            print(f"  ✅ {dump_file} ({file_size} bytes)")
        print("\nTo debug any crash dumps, use:")
        print(
            "  python -c \"import core_dump; import debug_interface; debug_interface.debug_core_dump(core_dump.load_core_dump('<dump_file>'))\""
        )
    else:
        print("\n❌ No core dump files found")

    # Clean up
    uninstall_global_handler()
