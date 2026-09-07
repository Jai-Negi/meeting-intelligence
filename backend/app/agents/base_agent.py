import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    success: bool
    data: Any = None
    error: str | None = None
    attempts: int = 1


class AgentError(Exception):
    pass


class BaseAgent(ABC):
    """
    Shared base class for all agents in the pipeline.

    Handles retries with backoff, per call timeouts, and consistent
    structured logging, so individual agents only need to implement
    their own `run` method and focus on their actual task.
    """

    name: str = "base_agent"
    max_retries: int = 3
    timeout_seconds: int = 60
    retry_backoff_seconds: float = 2.0

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """Implement the actual agent logic in subclasses."""
        raise NotImplementedError

    async def execute(self, **kwargs: Any) -> AgentResult:
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "agent execution started",
                    extra={"agent": self.name, "attempt": attempt},
                )

                result = await asyncio.wait_for(
                    self.run(**kwargs), timeout=self.timeout_seconds
                )

                logger.info(
                    "agent execution succeeded",
                    extra={"agent": self.name, "attempt": attempt},
                )

                return AgentResult(success=True, data=result, attempts=attempt)

            except asyncio.TimeoutError:
                last_error = AgentError(
                    f"{self.name} timed out after {self.timeout_seconds}s"
                )
                logger.warning(
                    "agent execution timed out",
                    extra={"agent": self.name, "attempt": attempt},
                )

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "agent execution failed",
                    extra={"agent": self.name, "attempt": attempt, "error": str(exc)},
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff_seconds * attempt)

        logger.error(
            "agent execution exhausted retries",
            extra={"agent": self.name, "attempts": self.max_retries},
        )

        return AgentResult(
            success=False,
            error=str(last_error) if last_error else "unknown error",
            attempts=self.max_retries,
        )
