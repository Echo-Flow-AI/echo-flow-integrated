from abc import ABC, abstractmethod
from typing import Any

from tool_interface import ToolResult


class BaseTool(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def run(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:
        pass