import asyncio
from typing import Any

from tool_base import BaseTool
from tool_interface import ToolResult


class SmartHomeTool(BaseTool):

    @property
    def name(self) -> str:
        return "smart_home"

    async def run(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:

        action = kwargs.get("action")
        device = kwargs.get("device")

        if not action or not device:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Both 'action' and 'device' are required.",
                retryable=False
            )

        await asyncio.sleep(0.2)

        if action == "turn_on":
            state = "on"

        elif action == "turn_off":
            state = "off"

        else:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error=f"Unsupported action: {action}",
                retryable=False
            )

        return ToolResult(
            task_id=task_id,
            tool_name=self.name,
            success=True,
            data={
                "device": device,
                "state": state
            }
        )


class FlightSearchTool(BaseTool):

    @property
    def name(self) -> str:
        return "flight_search"

    async def run(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:

        origin = kwargs.get("origin")
        destination = kwargs.get("destination")

        if not origin or not destination:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Both 'origin' and 'destination' are required.",
                retryable=False
            )

        await asyncio.sleep(0.5)

        return ToolResult(
            task_id=task_id,
            tool_name=self.name,
            success=True,
            data={
                "origin": origin,
                "destination": destination,
                "flights": [
                    {
                        "flight": "SJ101",
                        "departure": "09:00",
                        "arrival": "11:30"
                    },
                    {
                        "flight": "SJ202",
                        "departure": "14:00",
                        "arrival": "16:30"
                    }
                ]
            }
        )


class FlakyFlightSearchTool(BaseTool):

    def __init__(self):
        self.attempts = 0

    @property
    def name(self) -> str:
        return "flaky_flight_search"

    async def run(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:

        origin = kwargs.get("origin")
        destination = kwargs.get("destination")

        if not origin or not destination:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Both 'origin' and 'destination' are required.",
                retryable=False
            )

        self.attempts += 1

        await asyncio.sleep(0.3)

        if self.attempts < 3:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error=(
                    f"Temporary flight service failure "
                    f"on attempt {self.attempts}."
                ),
                retryable=True
            )

        return ToolResult(
            task_id=task_id,
            tool_name=self.name,
            success=True,
            data={
                "origin": origin,
                "destination": destination,
                "flight": "SJ999",
                "status": "available",
                "attempt": self.attempts
            }
        )


class HotelSearchTool(BaseTool):

    @property
    def name(self) -> str:
        return "hotel_search"

    async def run(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:

        city = kwargs.get("city")

        if not city:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="The 'city' argument is required.",
                retryable=False
            )

        await asyncio.sleep(0.5)

        return ToolResult(
            task_id=task_id,
            tool_name=self.name,
            success=True,
            data={
                "city": city,
                "hotels": [
                    {
                        "name": "Kernel Grand Hotel",
                        "rating": 4.5
                    },
                    {
                        "name": "AI Residency",
                        "rating": 4.2
                    }
                ]
            }
        )


# ============================================================
# LOCAL TOOL TEST
# ============================================================

async def main():

    task_id = "test-task-001"

    smart_home = SmartHomeTool()
    flight_search = FlightSearchTool()
    flaky_flight = FlakyFlightSearchTool()
    hotel_search = HotelSearchTool()

    print("\n--- Smart Home ---")

    result = await smart_home.run(
        task_id=task_id,
        action="turn_on",
        device="bedroom_light"
    )

    print(result)

    print("\n--- Flight Search ---")

    result = await flight_search.run(
        task_id=task_id,
        origin="Bengaluru",
        destination="Delhi"
    )

    print(result)

    print("\n--- Flaky Flight Search ---")

    for attempt in range(3):

        result = await flaky_flight.run(
            task_id=task_id,
            origin="Bengaluru",
            destination="Delhi"
        )

        print(f"Attempt {attempt + 1}: {result}")

    print("\n--- Hotel Search ---")

    result = await hotel_search.run(
        task_id=task_id,
        city="Bengaluru"
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())