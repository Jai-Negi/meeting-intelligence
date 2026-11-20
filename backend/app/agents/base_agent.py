import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.errors import PermanentError

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

    Retries wait exponentially longer each time, with random jitter so many
    jobs failing together do not all retry at the same moment. A
    PermanentError, or a missing file, ends the run at once, since trying
    again cannot help.
    """

    name: str = "base_agent"
    max_retries: int = 3
    timeout_seconds: int = 60
    retry_backoff_seconds: float = 2.0
    # Set to False when run() does its work in a thread. A timeout cannot stop
    # the thread, so a retry would run alongside the attempt it replaces.
    retry_on_timeout: bool = True

    def _backoff_delay(self, attempt: int) -> float:
        """Base delay doubled per attempt, scaled to between half and all of it."""
        return self.retry_backoff_seconds * 2 ** (attempt - 1) * random.uniform(0.5, 1.0)

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
                if not self.retry_on_timeout:
                    return self._give_up(last_error, attempt)

            except (PermanentError, FileNotFoundError) as exc:
                logger.error(
                    "agent execution failed permanently",
                    extra={"agent": self.name, "attempt": attempt, "error": str(exc)},
                )
                return self._give_up(exc, attempt)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "agent execution failed",
                    extra={"agent": self.name, "attempt": attempt, "error": str(exc)},
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff_delay(attempt))

        logger.error(
            "agent execution exhausted retries",
            extra={"agent": self.name, "attempts": self.max_retries},
        )
        return self._give_up(last_error, self.max_retries)

    def _give_up(self, error: Exception | None, attempts: int) -> AgentResult:
        return AgentResult(
            success=False,
            error=str(error) if error else "unknown error",
            attempts=attempts,
        )
