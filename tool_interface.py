from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    task_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None
    retryable: bool = False