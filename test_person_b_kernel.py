import asyncio

from kernel import Kernel


async def test_real_correction_flow():

    print("\n==============================")
    print("TEST: REAL PERSON B → KERNEL CORRECTION")
    print("==============================")

    kernel = Kernel()

    # Start original task
    old_task = kernel.start_task(
        "Find a flight from Bangalore to Delhi",
        slots={
            "origin": "Bangalore",
            "destination": "Delhi",
        },
    )

    old_task_id = old_task.task_id

    print("\nUser says:")
    print("Actually, make that Mumbai")

    # Kernel receives the interruption.
    new_task = await kernel.handle_interruption(
        "Actually, make that Mumbai"
    )

    # A new task must have been created.
    assert new_task is not None

    # New task must have a different ID.
    assert new_task.task_id != old_task_id

    # New task must be running.
    assert new_task.status.value == "running"

    # Original origin must remain.
    assert new_task.slots["origin"] == "Bangalore"

    # Destination must be corrected.
    assert new_task.slots["destination"] == "mumbai"

    # New goal must reflect the correction.
    assert new_task.goal == (
        "Find a flight from Bangalore to mumbai"
    )

    # Kernel must now point to the new task.
    assert kernel.current_task_id == new_task.task_id

    print("\nOld task:")
    print(old_task.task_id)

    print("New task:")
    print(new_task.task_id)

    print("New slots:")
    print(new_task.slots)

    print("New goal:")
    print(new_task.goal)

    print("\nPASS")


async def main():

    await test_real_correction_flow()

    print("\n================================")
    print("PERSON B → KERNEL INTEGRATION PASSED")
    print("================================")


if __name__ == "__main__":
    asyncio.run(main())