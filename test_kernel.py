import asyncio

from kernel import Kernel, TaskStatus


async def test_start_and_complete():
    print("\n==============================")
    print("TEST 1: START + COMPLETE")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    assert task.status == TaskStatus.RUNNING
    assert kernel.current_task_id == task.task_id

    result = kernel.complete_task(
        task.task_id,
        "result-1"
    )

    assert result is True
    assert task.status == TaskStatus.DONE

    print("PASS")


async def test_retry():
    print("\n==============================")
    print("TEST 2: FAIL + RETRY")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    kernel.fail_task(task.task_id)

    assert task.status == TaskStatus.FAILED

    kernel.retry_task(task.task_id)

    assert task.status == TaskStatus.RUNNING
    assert task.retry_count == 1

    print("PASS")


async def test_async_cancellation():
    print("\n==============================")
    print("TEST 3: ASYNC CANCELLATION")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Long running flight search"
    )

    kernel.start_async_task(task.task_id)

    await asyncio.sleep(0.1)

    await kernel.cancel_current_task()

    assert kernel.current_task is None
    assert kernel.current_task_id is None
    assert kernel._current_async_task is None

    print("PASS")


async def test_checkpoint():
    print("\n==============================")
    print("TEST 4: CHECKPOINT")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    kernel.save_checkpoint(
        task.task_id,
        3,
        {
            "origin": "Bangalore",
            "destination": "Delhi",
        },
    )

    assert task.current_step == 3
    assert task.checkpoint["origin"] == "Bangalore"

    checkpoint = kernel.load_checkpoint()

    assert checkpoint is not None
    assert checkpoint["current_step"] == 3
    assert checkpoint["checkpoint"]["destination"] == "Delhi"

    print("PASS")


async def test_restore():
    print("\n==============================")
    print("TEST 5: RESTORE")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    kernel.save_checkpoint(
        task.task_id,
        4,
        {
            "origin": "Bangalore",
            "destination": "Delhi",
        },
    )

    restored_kernel = Kernel()

    restored_task = restored_kernel.restore_task()

    assert restored_task is not None
    assert restored_task.goal == task.goal
    assert restored_task.current_step == 4
    assert restored_task.checkpoint["origin"] == "Bangalore"

    print("PASS")


async def test_late_result():
    print("\n==============================")
    print("TEST 6: LATE RESULT")
    print("==============================")

    kernel = Kernel()

    task_a = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    slow_task = asyncio.create_task(
        kernel.slow_async_task(task_a.task_id)
    )

    await asyncio.sleep(0.1)

    await kernel.cancel_current_task()

    task_b = kernel.start_task(
        "Find a flight from Bangalore to Mumbai"
    )

    late_result = await slow_task

    accepted = kernel.complete_task(
        late_result["task_id"],
        late_result["result_id"],
    )

    assert accepted is False
    assert kernel.current_task_id == task_b.task_id

    print("PASS")


async def test_duplicate_result():
    print("\n==============================")
    print("TEST 7: DUPLICATE RESULT")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    first = kernel.complete_task(
        task.task_id,
        "result-123",
    )

    second = kernel.complete_task(
        task.task_id,
        "result-123",
    )

    assert first is True
    assert second is False
    assert task.status == TaskStatus.DONE

    print("PASS")


async def main():

    await test_start_and_complete()
    await test_retry()
    await test_async_cancellation()
    await test_checkpoint()
    await test_restore()
    await test_late_result()
    await test_duplicate_result()

    print("\n================================")
    print("ALL CURRENT KERNEL TESTS PASSED")
    print("================================")


if __name__ == "__main__":
    asyncio.run(main())