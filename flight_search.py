import asyncio

from tool_base import BaseTool
from tool_interface import ToolResult


class FlightSearchTool(BaseTool):

    def __init__(self):
        self.attempt_count = 0

    @property
    def name(self) -> str:
        return "flight_search"

    async def run(
        self,
        task_id: str,
        **kwargs
    ) -> ToolResult:

        origin = kwargs.get("origin")
        destination = kwargs.get("destination")
        date = kwargs.get("date")
        trip_type = kwargs.get("trip_type")

        if not origin:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Origin is required",
                retryable=False
            )

        if not destination:
            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Destination is required",
                retryable=False
            )

        self.attempt_count += 1

        print("\n-----------------------------------")
        print(f"FLIGHT TOOL ATTEMPT {self.attempt_count}")
        print("-----------------------------------")

        print(f"Searching: {origin} -> {destination}")

        if date:
            print(f"Date: {date}")

        if trip_type:
            print(f"Trip type: {trip_type}")

        await asyncio.sleep(1)

        if self.attempt_count == 1:
            print("\nFLIGHT SEARCH FAILED")
            print("Error: Temporary flight service failure")

            return ToolResult(
                task_id=task_id,
                tool_name=self.name,
                success=False,
                error="Temporary flight service failure",
                retryable=True
            )

        print("\nFLIGHT SEARCH COMPLETED")

        result = {
            "origin": origin,
            "destination": destination,
            "date": date,
            "trip_type": trip_type,
            "message": f"Flight found from {origin} to {destination}"
        }

        return ToolResult(
            task_id=task_id,
            tool_name=self.name,
            success=True,
            data=result
        )