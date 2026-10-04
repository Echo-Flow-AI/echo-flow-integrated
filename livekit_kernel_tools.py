import json

from livekit.agents import function_tool

from kernel import Kernel


class LiveKitKernelTools:
    """
    Exposes the existing Samsung AI Kernel tools to LiveKit.

    All actual execution remains inside Kernel.execute_tool().
    """

    def __init__(self, kernel: Kernel):
        self.kernel = kernel
        self.task_id: str | None = None

    def start_task(self, goal: str) -> str:
        """Start a Kernel task for the current LiveKit conversation."""
        task = self.kernel.start_task(goal)
        self.task_id = task.task_id
        print(f"[KERNEL] LiveKit task started: {self.task_id}")
        return self.task_id

    def _require_task(self) -> str:
        if not self.task_id:
            raise RuntimeError(
                "No active Kernel task. Start a task before calling a tool."
            )

        return self.task_id

    async def _execute(
        self,
        tool_name: str,
        arguments: dict,
    ) -> str:
        task_id = self._require_task()

        print(
            f"[KERNEL] Executing {tool_name} "
            f"for task {task_id}"
        )

        result = await self.kernel.execute_tool(
            tool_name,
            task_id,
            **arguments,
        )

        output = {
            "task_id": result.task_id,
            "tool_name": result.tool_name,
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "retryable": result.retryable,
        }

        return json.dumps(output, default=str)

    @function_tool(
        name="smart_home",
        description=(
            "Control or query a smart-home device. "
            "Use this when the user asks for a smart-home action."
        ),
    )
    async def smart_home(
        self,
        device: str,
        action: str,
    ) -> str:
        return await self._execute(
            "smart_home",
            {
                "device": device,
                "action": action,
            },
        )

    @function_tool(
        name="flight_search",
        description=(
            "Search for flights between an origin and destination."
        ),
    )
    async def flight_search(
        self,
        origin: str,
        destination: str,
    ) -> str:
        return await self._execute(
            "flight_search",
            {
                "origin": origin,
                "destination": destination,
            },
        )

    @function_tool(
        name="hotel_search",
        description=(
            "Search for hotels in a requested destination."
        ),
    )
    async def hotel_search(
        self,
        destination: str,
    ) -> str:
        return await self._execute(
            "hotel_search",
            {
                "destination": destination,
            },
        )

    def get_tools(self):
        return [
            self.smart_home,
            self.flight_search,
            self.hotel_search,
        ]