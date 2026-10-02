import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interrupt_detector import (
    InterruptDetector,
    CORRECTION,
    ADDED_CONSTRAINT,
    GOAL_SWITCH,
    ABORT,
    NOISE,
)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING

    current_step: int = 0
    checkpoint: dict[str, Any] = field(default_factory=dict)

    retry_count: int = 0

    # Person B: structured information about the current goal
    slots: dict[str, Any] = field(default_factory=dict)


def create_task(
    goal: str,
    slots: dict[str, Any] | None = None,
) -> Task:
    return Task(
        task_id=str(uuid.uuid4()),
        goal=goal,
        slots=slots.copy() if slots else {},
    )


class Kernel:

    def __init__(self):
        self.current_task = None
        self.current_task_id = None

        self._current_async_task = None

        self.processed_results = set()
        self.max_retries = 3

        # Person B
        self.interrupt_detector = InterruptDetector()

    # ========================================================
    # START TASK
    # ========================================================

    def start_task(
        self,
        goal: str,
        slots: dict[str, Any] | None = None,
    ):
        task = create_task(goal, slots)

        task.status = TaskStatus.RUNNING

        self.current_task = task
        self.current_task_id = task.task_id

        print(f"Started task: {task.task_id}")
        print(f"Goal: {task.goal}")

        if task.slots:
            print(f"Slots: {task.slots}")

        return task

    # ========================================================
    # PERSON B — HANDLE USER INPUT
    # ========================================================

    def handle_user_input(
        self,
        new_text: str,
    ):
        """
        Classify new user input against the current task.

        Returns the InterruptionResult from Person B.
        """

        if self.current_task is None:
            return self.interrupt_detector.classify_interruption(
                new_text,
                {},
            )

        result = self.interrupt_detector.classify_interruption(
            new_text,
            self.current_task.slots,
        )

        print(
            f"Interruption classification: "
            f"{result.interruption_type}"
        )

        return result

    # ========================================================
    # PERSON B — HANDLE CORRECTION
    # ========================================================

    async def handle_user_correction(
        self,
        new_text: str,
    ):
        """
        Detect a correction, cancel the current task,
        merge the corrected slots, and start a new task.
        """

        if self.current_task is None:
            print("No current task.")
            return None

        old_task = self.current_task

        result = self.interrupt_detector.classify_interruption(
            new_text,
            old_task.slots,
        )

        if result.interruption_type != CORRECTION:
            print(
                "Input is not a correction. "
                f"Detected: {result.interruption_type}"
            )
            return None

        # Save the old goal information before cancellation.
        updated_slots = old_task.slots.copy()
        updated_slots.update(result.changed_slots)

        origin = updated_slots.get("origin")
        destination = updated_slots.get("destination")

        # Build the updated goal.
        if origin and destination:
            new_goal = (
                f"Find a flight from "
                f"{origin} to {destination}"
            )
        else:
            new_goal = old_task.goal

        print(
            f"Correction detected: "
            f"{result.changed_slots}"
        )

        # Cancel the old task.
        await self.cancel_current_task()

        # Start corrected task.
        new_task = self.start_task(
            new_goal,
            slots=updated_slots,
        )

        return new_task

    # ========================================================
    # PERSON B — HANDLE INTERRUPTION
    # ========================================================

    async def handle_interruption(
        self,
        new_text: str,
    ):
        """
        General Person B interruption handler.

        correction:
            cancel old task and create corrected task

        added_constraint:
            update current task slots

        goal_switch:
            cancel old task and start new goal

        abort:
            cancel current task

        noise:
            do nothing
        """

        if self.current_task is None:
            return self.handle_user_input(new_text)

        result = self.handle_user_input(new_text)

        # ----------------------------------------------------
        # NOISE
        # ----------------------------------------------------

        if result.interruption_type == NOISE:
            return result

        # ----------------------------------------------------
        # CORRECTION
        # ----------------------------------------------------

        if result.interruption_type == CORRECTION:
            return await self.handle_user_correction(new_text)

        # ----------------------------------------------------
        # ADDED CONSTRAINT
        # ----------------------------------------------------

        if result.interruption_type == ADDED_CONSTRAINT:

            self.current_task.slots.update(
                result.changed_slots
            )

            print(
                f"Added constraints: "
                f"{result.changed_slots}"
            )

            return self.current_task

        # ----------------------------------------------------
        # GOAL SWITCH
        # ----------------------------------------------------

        if result.interruption_type == GOAL_SWITCH:

            new_goal = result.new_goal or new_text

            await self.cancel_current_task()

            return self.start_task(
                new_goal,
                slots={},
            )

        # ----------------------------------------------------
        # ABORT
        # ----------------------------------------------------

        if result.interruption_type == ABORT:

            await self.cancel_current_task()

            return None

        return result

    # ========================================================
    # COMPLETE TASK
    # ========================================================

    def complete_task(
        self,
        task_id: str,
        result_id: str,
    ):
        if self.current_task is None:
            print("No current task.")
            return False

        if task_id != self.current_task_id:
            print("Ignoring result from old task.")
            return False

        if result_id in self.processed_results:
            print("Ignoring duplicate result.")
            return False

        self.processed_results.add(result_id)

        self.current_task.status = TaskStatus.DONE

        print(f"Task {task_id} completed.")

        self.clear_checkpoint()

        return True

    # ========================================================
    # FAIL TASK
    # ========================================================

    def fail_task(self, task_id: str):

        if self.current_task is None:
            print("No current task.")
            return

        if task_id != self.current_task_id:
            print("Ignoring failure from old task.")
            return

        self.current_task.status = TaskStatus.FAILED

        print(f"Task {task_id} failed.")

    # ========================================================
    # RETRY TASK
    # ========================================================

    def retry_task(self, task_id: str):

        if self.current_task is None:
            print("No current task.")
            return

        if task_id != self.current_task_id:
            print("Ignoring retry from old task.")
            return

        if self.current_task.status != TaskStatus.FAILED:
            print("Task is not failed. Cannot retry.")
            return

        if self.current_task.retry_count >= self.max_retries:
            print("Maximum retry limit reached.")
            return

        self.current_task.retry_count += 1
        self.current_task.status = TaskStatus.RUNNING

        print(f"Retrying task {task_id}...")
        print(f"Retry count: {self.current_task.retry_count}")

    # ========================================================
    # RUN ASYNC TASK
    # ========================================================

    async def run_async_task(self, task_id: str):

        print(f"Async task {task_id} started.")

        try:
            for i in range(10):
                await asyncio.sleep(1)
                print(
                    f"Async task {task_id}: "
                    f"{i + 1} seconds"
                )

            print(
                f"Async task {task_id} finished."
            )

        except asyncio.CancelledError:

            print(
                f"Async task {task_id} was cancelled."
            )

            raise

    # ========================================================
    # START ASYNC TASK
    # ========================================================

    def start_async_task(self, task_id: str):

        self._current_async_task = asyncio.create_task(
            self.run_async_task(task_id)
        )

        print("Async task created.")

    # ========================================================
    # CANCEL CURRENT TASK
    # ========================================================

    async def cancel_current_task(self):

        if self.current_task is None:
            print("No current task to cancel.")
            return

        if self.current_task.status != TaskStatus.RUNNING:
            print("Current task is not running.")
            return

        task_id = self.current_task_id

        self.current_task.status = TaskStatus.CANCELLED

        print(f"Task {task_id} cancelled.")

        if self._current_async_task is not None:

            self._current_async_task.cancel()

            try:
                await self._current_async_task

            except asyncio.CancelledError:
                print(
                    "Async task cancellation confirmed."
                )

        self.current_task = None
        self.current_task_id = None
        self._current_async_task = None

    # ========================================================
    # SAVE CHECKPOINT
    # ========================================================

    def save_checkpoint(
        self,
        task_id: str,
        step: int,
        data: dict,
    ):

        if self.current_task is None:
            print("No current task.")
            return

        if task_id != self.current_task_id:
            print("Ignoring checkpoint from old task.")
            return

        self.current_task.current_step = step
        self.current_task.checkpoint = data.copy()

        checkpoint_data = {
            "task_id": task_id,
            "goal": self.current_task.goal,
            "current_step": step,
            "checkpoint": data,
            "slots": self.current_task.slots,
        }

        with open(
            "checkpoint.json",
            "w",
        ) as file:
            json.dump(
                checkpoint_data,
                file,
                indent=4,
            )

        print(
            f"Checkpoint saved at step {step}."
        )

    # ========================================================
    # LOAD CHECKPOINT
    # ========================================================

    def load_checkpoint(self):

        try:

            with open(
                "checkpoint.json",
                "r",
            ) as file:

                data = json.load(file)

            print("Checkpoint loaded.")
            print("Goal:", data["goal"])
            print("Step:", data["current_step"])
            print("Data:", data["checkpoint"])

            return data

        except FileNotFoundError:

            print("No checkpoint found.")

            return None

    # ========================================================
    # RESUME TASK
    # ========================================================

    def resume_task(self, task_id: str):

        if self.current_task is None:
            print("No current task.")
            return

        if task_id != self.current_task_id:
            print("Cannot resume old task.")
            return

        self.current_task.status = TaskStatus.RUNNING

        print(
            f"Resuming task from step "
            f"{self.current_task.current_step}."
        )

        print(
            f"Checkpoint: "
            f"{self.current_task.checkpoint}"
        )

    # ========================================================
    # GET RESUME POINT
    # ========================================================

    def get_resume_point(self, task_id: str):

        if self.current_task is None:
            print("No current task.")
            return

        if task_id != self.current_task_id:
            print("Cannot get resume point for old task.")
            return

        print(
            f"Resume from step: "
            f"{self.current_task.current_step}"
        )

        print(
            f"Saved data: "
            f"{self.current_task.checkpoint}"
        )

        return (
            self.current_task.current_step,
            self.current_task.checkpoint,
        )

    # ========================================================
    # RESTORE TASK
    # ========================================================

    def restore_task(self):

        data = self.load_checkpoint()

        if data is None:
            return None

        task = Task(
            task_id=data["task_id"],
            goal=data["goal"],
            status=TaskStatus.RUNNING,
            current_step=data["current_step"],
            checkpoint=data["checkpoint"],
            slots=data.get("slots", {}),
        )

        self.current_task = task
        self.current_task_id = task.task_id

        print(
            f"Task restored: {task.task_id}"
        )

        print(
            f"Resuming from step: "
            f"{task.current_step}"
        )

        return task

    # ========================================================
    # CLEAR CHECKPOINT
    # ========================================================

    def clear_checkpoint(self):

        import os

        if os.path.exists("checkpoint.json"):

            os.remove("checkpoint.json")

            print("Checkpoint cleared.")

        else:

            print("No checkpoint to clear.")

    # ========================================================
    # SLOW ASYNC TASK
    # ========================================================

    async def slow_async_task(
        self,
        task_id: str,
    ):

        print(
            f"Slow task {task_id} started."
        )

        try:

            await asyncio.sleep(5)

            print(
                f"Slow task {task_id} finished."
            )

            return {
                "task_id": task_id,
                "result_id": f"result-{task_id}",
            }

        except asyncio.CancelledError:

            print(
                f"Slow task {task_id} cancelled."
            )

            return {
                "task_id": task_id,
                "result_id": f"late-result-{task_id}",
            }


if __name__ == "__main__":

    async def main():

        kernel = Kernel()

        task_a = kernel.start_task(
            "Find a flight from Mumbai to Delhi",
            slots={
                "origin": "Mumbai",
                "destination": "Delhi",
            },
        )

        kernel._current_async_task = asyncio.create_task(
            kernel.slow_async_task(
                task_a.task_id
            )
        )

        await asyncio.sleep(1)

        print("\nCancelling Task A...")

        await kernel.cancel_current_task()

        print("\nStarting Task B...")

        task_b = kernel.start_task(
            "Find a flight from Mumbai to Bangalore",
            slots={
                "origin": "Mumbai",
                "destination": "Bangalore",
            },
        )

        print("\nLate result from Task A arrives...")

        kernel.complete_task(
            task_a.task_id,
            "late-result-A",
        )

        print("\nCompleting Task B...")

        kernel.complete_task(
            task_b.task_id,
            "result-B",
        )

        print("\nFinal Task B status:")
        print(task_b.status.value)

    asyncio.run(main())