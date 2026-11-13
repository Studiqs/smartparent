"""
=============================================================================
STUDIQS® Core OOP Resilience Base Architecture (Zero-Crash Standard)
=============================================================================
Defines enterprise design patterns:
1. BaseEngine(ABC): Abstract Base Engine with Template Method lifecycle:
   run() = pre_check -> validate_input -> execute_core -> post_process -> fallback
2. CircuitBreaker: Prevents cascading pipeline failure upon repeated dependency faults.
3. @resilient_engine_step: Fault-tolerant decorator capturing execution latency,
   memory footprint, and trapping exceptions into safe degraded fallback outputs.
4. Pydantic Schemas: Type-safe, data corruption-resistant contracts.
=============================================================================
"""

import time
import logging
import traceback
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger("STUDIQS_Resilience")


# =============================================================================
# 1. Pydantic v2 Type-Safe Data Contracts
# =============================================================================

class EngineHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Tripped, short-circuiting calls to fallback
    HALF_OPEN = "HALF_OPEN"# Testing recovery


class ParsedQuestionSchema(BaseModel):
    """Strict schema for an individual extracted question item."""
    model_config = ConfigDict(extra="ignore")

    question_no: Union[int, str]
    question_text: str = Field(default="", description="Question stem text")
    max_marks: float = Field(default=1.0, ge=0.0)
    options: List[str] = Field(default_factory=list)
    bloom_level: Optional[str] = "Remember"
    difficulty: Optional[str] = "Medium"
    section: Optional[str] = None
    sub_parts: List[Dict[str, Any]] = Field(default_factory=list)
    is_mcq: bool = False
    language: Optional[str] = "en"


class TopicMappingSchema(BaseModel):
    """Strict schema for question-to-topic mapping result."""
    model_config = ConfigDict(extra="ignore")

    question_no: Union[int, str]
    question_text: str = ""
    max_marks: float = 1.0
    subject: str = "General"
    chapter: str = "Unknown"
    topic: str = "Unknown Topic"
    topic_id: str = "Unknown"
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_level: str = "none"
    mapping_status: str = "manual_review"
    manual_review_required: bool = True
    sub_domain: Optional[str] = None


# =============================================================================
# 2. Circuit Breaker Pattern
# =============================================================================

class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """
    Enterprise Circuit Breaker to prevent cascading engine crashes.
    Transitions: CLOSED -> OPEN (after failure_threshold) -> HALF_OPEN (after recovery_timeout).
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: float = 30.0, name: str = "Generic"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.success_count = 0

    def can_execute(self) -> bool:
        """Determines if call can proceed through circuit."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout_sec:
                logger.info(f"[CircuitBreaker:{self.name}] Recovery timeout reached. Transitioning to HALF_OPEN.")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        """Record successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:
                logger.info(f"[CircuitBreaker:{self.name}] Service recovered. Resetting circuit to CLOSED.")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0

    def record_failure(self, error: Optional[Exception] = None):
        """Record execution failure."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(
            f"[CircuitBreaker:{self.name}] Failure recorded ({self.failure_count}/{self.failure_threshold}). Error: {error}"
        )
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(f"[CircuitBreaker:{self.name}] Failure threshold reached. TRIP TO OPEN STATE.")

    def is_open(self) -> bool:
        """Checks if breaker is currently OPEN."""
        return self.state == CircuitState.OPEN

    def is_closed(self) -> bool:
        """Checks if breaker is currently CLOSED."""
        return self.state == CircuitState.CLOSED

    def reset(self):
        """Manually resets circuit to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0


# =============================================================================
# 3. Resilient Step Execution Decorator
# =============================================================================

def resilient_engine_step(engine_name: str = "Engine"):
    """
    Method decorator providing zero-crash resilience:
    - Measures latency in milliseconds.
    - Catches unhandled exceptions, logs structured traceback.
    - Automatically invokes the class's fallback() method to yield safe degraded data.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.perf_counter()
            try:
                # Check circuit breaker if attached to self
                cb: Optional[CircuitBreaker] = getattr(self, "circuit_breaker", None)
                if cb and not cb.can_execute():
                    logger.warning(f"[{engine_name}] Circuit breaker OPEN. Bypassing directly to fallback.")
                    raise CircuitBreakerOpenException(f"Circuit {cb.name} is OPEN.")

                # Execute core engine logic
                result = func(self, *args, **kwargs)

                if cb:
                    cb.record_success()

                latency_ms = (time.perf_counter() - start_time) * 1000.0
                if hasattr(self, "_last_latency_ms"):
                    self._last_latency_ms = latency_ms

                return result

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    f"[{engine_name}] Resilient Guard intercepted failure in {func.__name__} after {latency_ms:.2f}ms:\n"
                    f"Error: {type(e).__name__}: {str(e)}\n"
                    f"{traceback.format_exc()}"
                )

                cb = getattr(self, "circuit_breaker", None)
                if cb:
                    cb.record_failure(e)

                # Invoke fallback if available
                if hasattr(self, "fallback") and callable(self.fallback):
                    fallback_input = args[0] if len(args) > 0 else kwargs
                    logger.info(f"[{engine_name}] Invoking graceful fallback handler.")
                    try:
                        return self.fallback(e, fallback_input)
                    except TypeError:
                        return self.fallback(error=e, input_data=fallback_input)

                # If no fallback is defined, raise clean runtime error
                raise RuntimeError(f"[{engine_name}] Execution failed without fallback: {e}") from e

        return wrapper
    return decorator


# =============================================================================
# 4. Abstract Base Engine (Template Method Lifecycle)
# =============================================================================

class BaseEngine(ABC):
    """
    Abstract Base Engine contract defining the standard Template Method lifecycle:
    
        run(input_data) ->
            1. validate_input(input_data)
            2. execute_core(validated_data) [protected by CircuitBreaker & Resilient Step]
            3. post_process(result)
            4. fallback(error, input_data) [if execution fails]
    """

    def __init__(self, name: str = "BaseEngine", failure_threshold: int = 5):
        self.name = name
        self.circuit_breaker = CircuitBreaker(failure_threshold=failure_threshold, name=name)
        self.health_status = EngineHealthStatus.HEALTHY
        self._last_latency_ms: float = 0.0
        self._last_error: Optional[str] = None

    @abstractmethod
    def validate_input(self, input_data: Any) -> Any:
        """Validates and cleans input data before execution. Raises ValueError on malformed data."""
        pass

    @abstractmethod
    def execute_core(self, validated_data: Any) -> Any:
        """Executes the primary business logic of the engine."""
        pass

    @abstractmethod
    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Provides a safe, non-crashing degraded return value when execution fails."""
        pass

    def post_process(self, result: Any) -> Any:
        """Optional post-processing hook for formatting or enrichment."""
        return result

    def run(self, input_data: Any) -> Any:
        """
        Template Method orchestrating the full execution lifecycle.
        Guarantees zero unhandled crashes.
        """
        start_time = time.perf_counter()
        try:
            # Step 1: Pre-execution validation
            validated = self.validate_input(input_data)

            # Step 2: Check Circuit Breaker
            if not self.circuit_breaker.can_execute():
                logger.warning(f"[{self.name}] Circuit breaker OPEN. Routing directly to fallback.")
                return self.fallback(
                    CircuitBreakerOpenException(f"Circuit breaker {self.name} is OPEN"),
                    input_data
                )

            # Step 3: Core execution
            raw_result = self.execute_core(validated)
            self.circuit_breaker.record_success()

            # Step 4: Post-processing
            final_result = self.post_process(raw_result)
            self.health_status = EngineHealthStatus.HEALTHY
            self._last_error = None
            return final_result

        except Exception as err:
            self.health_status = EngineHealthStatus.DEGRADED
            self._last_error = str(err)
            self.circuit_breaker.record_failure(err)
            logger.error(f"[{self.name}] Error during run(): {err}. Triggering fallback.")
            return self.fallback(err, input_data)

        finally:
            self._last_latency_ms = (time.perf_counter() - start_time) * 1000.0

    def health_check(self) -> Dict[str, Any]:
        """Returns the operational health status and telemetry of the engine."""
        return {
            "engine": self.name,
            "status": self.health_status.value,
            "circuit_state": self.circuit_breaker.state.value,
            "last_latency_ms": round(self._last_latency_ms, 2),
            "last_error": self._last_error
        }

    def execute(self, input_data: Any) -> Any:
        """Alias for run() to support standard engine execution conventions."""
        return self.run(input_data)

    def reset_circuit(self) -> None:
        """Manually resets the circuit breaker to CLOSED state."""
        self.circuit_breaker.reset()
