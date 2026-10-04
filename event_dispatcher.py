from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Awaitable, Callable

from kernel_events import EventStream, KernelEvent, KernelEventType


EventHandler = Callable[[KernelEvent], Any]


class EventDispatcher:
    """
    Routes Kernel events from an EventStream to registered handlers.

    Responsibilities:
    - Subscribe to a Kernel EventStream.
    - Route events by event type.
    - Support sync and async handlers.
    - Isolate handler failures.
    - Prevent one bad handler from breaking the Kernel event pipeline.
    """

    def __init__(self, event_stream: EventStream):
        self.event_stream = event_stream
        self._handlers: dict[KernelEventType, list[EventHandler]] = defaultdict(list)
        self._attached = False

    def attach(self) -> None:
        """
        Attach the dispatcher to the EventStream.
        """
        if self._attached:
            return

        self.event_stream.subscribe(self._handle_event)
        self._attached = True

    def detach(self) -> None:
        """
        Detach the dispatcher from the EventStream.
        """
        if not self._attached:
            return

        self.event_stream.unsubscribe(self._handle_event)
        self._attached = False

    def subscribe(
        self,
        event_type: KernelEventType,
        handler: EventHandler,
    ) -> None:
        """
        Register a handler for a specific event type.
        """
        handlers = self._handlers[event_type]

        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(
        self,
        event_type: KernelEventType,
        handler: EventHandler,
    ) -> None:
        """
        Remove a handler from a specific event type.
        """
        handlers = self._handlers.get(event_type)

        if not handlers:
            return

        if handler in handlers:
            handlers.remove(handler)

        if not handlers:
            self._handlers.pop(event_type, None)

    def handler_count(
        self,
        event_type: KernelEventType | None = None,
    ) -> int:
        """
        Return the number of registered handlers.

        If event_type is supplied, return handlers for that event type.
        Otherwise return the total number of handlers.
        """
        if event_type is not None:
            return len(self._handlers.get(event_type, []))

        return sum(len(handlers) for handlers in self._handlers.values())

    def _handle_event(self, event: KernelEvent) -> None | Awaitable[None]:
        """
        Receive an event from EventStream and dispatch it
        to all matching handlers.
        """
        handlers = list(self._handlers.get(event.event_type, []))

        if not handlers:
            return None

        async def dispatch_handlers() -> None:
            for handler in handlers:
                try:
                    result = handler(event)

                    if inspect.isawaitable(result):
                        await result

                except Exception as exc:
                    print(
                        "[DISPATCHER WARNING] "
                        f"Handler failed for {event.event_type.value}: {exc}"
                    )

        return dispatch_handlers()

    def clear(self) -> None:
        """
        Remove all registered handlers.
        """
        self._handlers.clear()


async def dispatcher_test() -> None:
    """
    Local test for the EventDispatcher.
    """

    event_stream = EventStream()
    dispatcher = EventDispatcher(event_stream)

    received_events: list[str] = []

    def task_started_handler(event: KernelEvent) -> None:
        received_events.append(
            f"sync:{event.event_type.value}"
        )

    async def task_completed_handler(event: KernelEvent) -> None:
        await asyncio.sleep(0.05)

        received_events.append(
            f"async:{event.event_type.value}"
        )

    dispatcher.subscribe(
        KernelEventType.TASK_STARTED,
        task_started_handler,
    )

    dispatcher.subscribe(
        KernelEventType.TASK_COMPLETED,
        task_completed_handler,
    )

    dispatcher.attach()

    task_started_event = KernelEvent(
        event_type=KernelEventType.TASK_STARTED,
        task_id="dispatcher-test-task",
    )

    task_completed_event = KernelEvent(
        event_type=KernelEventType.TASK_COMPLETED,
        task_id="dispatcher-test-task",
    )

    event_stream.emit(task_started_event)
    event_stream.emit(task_completed_event)

    await asyncio.sleep(0.1)

    assert received_events == [
        "sync:task_started",
        "async:task_completed",
    ], received_events

    assert dispatcher.handler_count(
        KernelEventType.TASK_STARTED
    ) == 1

    assert dispatcher.handler_count(
        KernelEventType.TASK_COMPLETED
    ) == 1

    assert dispatcher.handler_count() == 2

    dispatcher.unsubscribe(
        KernelEventType.TASK_STARTED,
        task_started_handler,
    )

    assert dispatcher.handler_count(
        KernelEventType.TASK_STARTED
    ) == 0

    dispatcher.detach()

    assert dispatcher._attached is False

    print("EVENT DISPATCHER TEST PASSED")


if __name__ == "__main__":
    asyncio.run(dispatcher_test())
