import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


# ==========================================================
# EVENT TYPES
# ==========================================================

class KernelEventType(Enum):

    TASK_STARTED = "task_started"

    TOOL_STARTED = "tool_started"

    TOOL_COMPLETED = "tool_completed"

    TOOL_FAILED = "tool_failed"

    CHECKPOINT_SAVED = "checkpoint_saved"

    TASK_CANCELLED = "task_cancelled"

    TASK_COMPLETED = "task_completed"

    TASK_FAILED = "task_failed"


# ==========================================================
# KERNEL EVENT
# ==========================================================

@dataclass
class KernelEvent:

    event_type: KernelEventType

    task_id: str

    timestamp: str = field(
        default_factory=lambda: (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    event_id: str = field(
        default_factory=lambda: str(
            uuid.uuid4()
        )
    )

    tool_name: str | None = None

    step_name: str | None = None

    checkpoint: str | None = None

    data: Any = None

    error: str | None = None


# ==========================================================
# EVENT HANDLER
# ==========================================================

EventHandler = Callable[
    [KernelEvent],
    Any
]


# ==========================================================
# EVENT STREAM
# ==========================================================

class EventStream:

    def __init__(self):

        self.events: list[
            KernelEvent
        ] = []

        self._subscribers: list[
            EventHandler
        ] = []

    # ------------------------------------------------------
    # SUBSCRIBE
    # ------------------------------------------------------

    def subscribe(
        self,
        handler: EventHandler
    ):

        if handler not in self._subscribers:

            self._subscribers.append(
                handler
            )

    # ------------------------------------------------------
    # UNSUBSCRIBE
    # ------------------------------------------------------

    def unsubscribe(
        self,
        handler: EventHandler
    ):

        if handler in self._subscribers:

            self._subscribers.remove(
                handler
            )

    # ------------------------------------------------------
    # EMIT EVENT
    # ------------------------------------------------------

    def emit(
        self,
        event: KernelEvent
    ):

        # --------------------------------------------------
        # STORE EVENT
        # --------------------------------------------------

        self.events.append(
            event
        )

        # --------------------------------------------------
        # PRINT EVENT
        # --------------------------------------------------

        print()
        print(
            f"[EVENT] "
            f"{event.event_type.value}"
        )

        print(
            f"Task: {event.task_id}"
        )

        if event.tool_name:

            print(
                f"Tool: {event.tool_name}"
            )

        if event.step_name:

            print(
                f"Step: {event.step_name}"
            )

        if event.checkpoint:

            print(
                f"Checkpoint: "
                f"{event.checkpoint}"
            )

        if event.error:

            print(
                f"Error: {event.error}"
            )

        # --------------------------------------------------
        # NOTIFY SUBSCRIBERS
        # --------------------------------------------------

        for subscriber in list(
            self._subscribers
        ):

            try:

                result = subscriber(
                    event
                )

                # ------------------------------------------
                # ASYNC SUBSCRIBER
                # ------------------------------------------

                if inspect.isawaitable(
                    result
                ):

                    try:

                        loop = (
                            asyncio.get_running_loop()
                        )

                    except RuntimeError:

                        asyncio.run(
                            result
                        )

                    else:

                        loop.create_task(
                            self._handle_async_subscriber(
                                result
                            )
                        )

            except Exception as error:

                # ------------------------------------------
                # SUBSCRIBER FAILURE ISOLATION
                # ------------------------------------------

                print(
                    f"[EVENT WARNING] "
                    f"Subscriber failed: "
                    f"{error}"
                )

    # ------------------------------------------------------
    # ASYNC SUBSCRIBER HANDLER
    # ------------------------------------------------------

    async def _handle_async_subscriber(
        self,
        awaitable
    ):

        try:

            await awaitable

        except Exception as error:

            print(
                f"[EVENT WARNING] "
                f"Async subscriber failed: "
                f"{error}"
            )

    # ------------------------------------------------------
    # GET ALL EVENTS
    # ------------------------------------------------------

    def get_events(
        self
    ) -> list[KernelEvent]:

        return list(
            self.events
        )

    # ------------------------------------------------------
    # GET TASK EVENTS
    # ------------------------------------------------------

    def get_task_events(
        self,
        task_id: str
    ) -> list[KernelEvent]:

        return [
            event
            for event in self.events
            if event.task_id == task_id
        ]

    # ------------------------------------------------------
    # SUBSCRIBER COUNT
    # ------------------------------------------------------

    def subscriber_count(
        self
    ) -> int:

        return len(
            self._subscribers
        )

    # ------------------------------------------------------
    # CLEAR EVENTS
    # ------------------------------------------------------

    def clear(self):

        self.events.clear()


# ==========================================================
# EVENT FACTORY
# ==========================================================

def create_event(
    event_type: KernelEventType,
    task_id: str,
    **kwargs: Any
) -> KernelEvent:

    return KernelEvent(
        event_type=event_type,
        task_id=task_id,
        **kwargs
    )


# ==========================================================
# BASIC EVENT STREAM TEST
# ==========================================================

def event_stream_test():

    print()
    print("=" * 70)
    print(
        "          KERNEL EVENT STREAM TEST"
    )
    print("=" * 70)

    stream = EventStream()

    received_events: list[
        KernelEvent
    ] = []

    # ------------------------------------------------------
    # SUBSCRIBER
    # ------------------------------------------------------

    def event_listener(
        event: KernelEvent
    ):

        received_events.append(
            event
        )

        print(
            f"[SUBSCRIBER] "
            f"Received: "
            f"{event.event_type.value}"
        )

    # ------------------------------------------------------
    # SUBSCRIBE
    # ------------------------------------------------------

    stream.subscribe(
        event_listener
    )

    assert (
        stream.subscriber_count()
        == 1
    )

    task_id = (
        "test-task-001"
    )

    # ------------------------------------------------------
    # EMIT EVENTS
    # ------------------------------------------------------

    stream.emit(
        create_event(
            KernelEventType.TASK_STARTED,
            task_id
        )
    )

    stream.emit(
        create_event(
            KernelEventType.TOOL_STARTED,
            task_id,
            tool_name="flight_search"
        )
    )

    stream.emit(
        create_event(
            KernelEventType.TOOL_COMPLETED,
            task_id,
            tool_name="flight_search",
            data={
                "status": "success"
            }
        )
    )

    stream.emit(
        create_event(
            KernelEventType.TASK_COMPLETED,
            task_id
        )
    )

    # ------------------------------------------------------
    # VERIFY STORAGE
    # ------------------------------------------------------

    events = (
        stream.get_events()
    )

    assert len(events) == 4

    # ------------------------------------------------------
    # VERIFY SUBSCRIBER
    # ------------------------------------------------------

    assert len(
        received_events
    ) == 4

    # ------------------------------------------------------
    # VERIFY EVENT IDs
    # ------------------------------------------------------

    assert (
        events[0].event_id
        != events[1].event_id
    )

    # ------------------------------------------------------
    # UNSUBSCRIBE
    # ------------------------------------------------------

    stream.unsubscribe(
        event_listener
    )

    assert (
        stream.subscriber_count()
        == 0
    )

    print()
    print(
        "Events stored:",
        len(stream.get_events())
    )

    print(
        "Events received by subscriber:",
        len(received_events)
    )

    print()
    print(
        "KERNEL EVENT STREAM TEST PASSED"
    )


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    event_stream_test()