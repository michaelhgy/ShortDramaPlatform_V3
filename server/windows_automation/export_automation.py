"""Side-effect boundaries for the V1 Jianying export executor.

The production Windows adapters are intentionally not implemented here.  This
module defines the evidence and safety rules they must satisfy before an input
action is allowed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence


class ExportAutomationError(RuntimeError):
    """A structured stop condition for a page-recognition or action attempt."""

    def __init__(self, code: str, message: str, *, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.evidence = evidence or {}


@dataclass(frozen=True)
class PageSnapshot:
    """A timestamped view of the foreground Jianying window."""

    window_handle: str
    captured_at: float
    screenshot_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageCheck:
    condition: str
    matched: bool
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocatorCandidate:
    locator: str
    x: int
    y: int
    score: float
    strategy: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportAction:
    action_id: str
    locator: str
    precondition: str
    postcondition: str
    timeout_seconds: float
    input_kind: str = "click"
    input_text: str = ""
    wait_for_postcondition: bool = True

    def __post_init__(self) -> None:
        if not self.action_id or not self.locator or not self.precondition or not self.postcondition:
            raise ValueError("导出动作必须声明标识、定位器和前后置页面条件")
        if self.timeout_seconds <= 0:
            raise ValueError("导出动作 timeout_seconds 必须大于零")
        if self.input_kind not in {"click", "replace_text", "choose_folder", "verify"}:
            raise ValueError("导出动作 input_kind 不受支持")
        if self.input_kind in {"replace_text", "choose_folder"} and not self.input_text:
            raise ValueError("文本输入动作必须提供 input_text")
        if not self.wait_for_postcondition and self.input_kind != "click":
            raise ValueError("只有点击动作可以跳过后置页面等待")


@dataclass(frozen=True)
class ActionRun:
    action_id: str
    elapsed_ms: int
    evidence: dict[str, Any]


class PageObserver(Protocol):
    def capture(self) -> PageSnapshot: ...

    def check(self, snapshot: PageSnapshot, condition: str) -> PageCheck: ...


class AnchorLocator(Protocol):
    def locate(self, snapshot: PageSnapshot, locator: str) -> Sequence[LocatorCandidate]: ...


class InputActuator(Protocol):
    def perform(self, action: ExportAction, candidate: LocatorCandidate) -> dict[str, Any]: ...


@dataclass(frozen=True)
class OcrRegion:
    """A bounded crop. OCR callers must never submit an entire window by default."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("OCR 区域必须是有效的局部矩形")


@dataclass(frozen=True)
class OcrRead:
    text: str
    confidence: float
    elapsed_ms: int
    region: OcrRegion
    evidence: dict[str, Any] = field(default_factory=dict)


class LocalOcr(Protocol):
    def read(self, region: OcrRegion) -> tuple[str, float, dict[str, Any]]: ...


def read_local_ocr_with_budget(
    reader: LocalOcr,
    region: OcrRegion,
    maximum_seconds: float,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> OcrRead:
    """Read one local crop and stop the action when its time budget is exceeded."""
    if maximum_seconds <= 0:
        raise ValueError("OCR 时间预算必须大于零")
    started_at = clock()
    text, confidence, evidence = reader.read(region)
    elapsed_ms = round((clock() - started_at) * 1000)
    result = OcrRead(str(text), float(confidence), elapsed_ms, region, evidence)
    if elapsed_ms > maximum_seconds * 1000:
        raise ExportAutomationError(
            "OCR_BUDGET_EXCEEDED",
            "本地 OCR 超出本动作时间预算，已停止继续执行",
            evidence={
                "elapsed_ms": elapsed_ms,
                "maximum_ms": round(maximum_seconds * 1000),
                "region": {"x": region.x, "y": region.y, "width": region.width, "height": region.height},
                "ocr": evidence,
            },
        )
    return result


def choose_unique_candidate(
    candidates: Sequence[LocatorCandidate], minimum_score: float
) -> LocatorCandidate:
    """Accept exactly one high-confidence candidate, otherwise stop safely."""
    if not 0 < minimum_score <= 1:
        raise ValueError("定位最低置信度必须在 0 到 1 之间")
    qualified = [candidate for candidate in candidates if candidate.score >= minimum_score]
    evidence = {
        "minimum_score": minimum_score,
        "candidates": [
            {
                "locator": item.locator,
                "score": item.score,
                "strategy": item.strategy,
                "x": item.x,
                "y": item.y,
            }
            for item in candidates
        ],
    }
    if not qualified:
        raise ExportAutomationError(
            "LOCATOR_NOT_FOUND", "未找到达到置信度阈值的唯一定位结果", evidence=evidence
        )
    if len(qualified) != 1:
        raise ExportAutomationError(
            "LOCATOR_AMBIGUOUS", "定位结果不唯一，已停止执行", evidence=evidence
        )
    return qualified[0]


class PageActionRunner:
    """Runs one verified action with a fresh pre-check and postcondition wait."""

    def __init__(
        self,
        observer: PageObserver,
        locator: AnchorLocator,
        actuator: InputActuator,
        *,
        minimum_score: float = 0.82,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval_seconds: float = 0.1,
        abort_requested: Callable[[], bool] | None = None,
        recovery: Callable[[ExportAction, int, ExportAutomationError], None] | None = None,
        maximum_attempts: int = 1,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("页面轮询间隔必须大于零")
        if maximum_attempts <= 0:
            raise ValueError("maximum_attempts must be positive")
        self.observer = observer
        self.locator = locator
        self.actuator = actuator
        self.minimum_score = minimum_score
        self.clock = clock
        self.sleep = sleep
        self.poll_interval_seconds = poll_interval_seconds
        self.abort_requested = abort_requested or (lambda: False)
        self.recovery = recovery
        self.maximum_attempts = maximum_attempts

    def run(self, action: ExportAction) -> ActionRun:
        for attempt in range(1, self.maximum_attempts + 1):
            try:
                return self._run_once(action)
            except ExportAutomationError as exc:
                recoverable = exc.code in {"PRECONDITION_FAILED", "LOCATOR_NOT_FOUND", "LOCATOR_AMBIGUOUS"}
                if not recoverable or attempt >= self.maximum_attempts or self.recovery is None:
                    raise
                self._ensure_not_aborted(action)
                self.recovery(action, attempt, exc)
                self.sleep(self.poll_interval_seconds)
        raise AssertionError("unreachable")

    def _run_once(self, action: ExportAction) -> ActionRun:
        started_at = self.clock()
        self._ensure_not_aborted(action)
        before = self.observer.capture()
        precheck = self.observer.check(before, action.precondition)
        if not precheck.matched:
            raise ExportAutomationError(
                "PRECONDITION_FAILED",
                f"当前页面不满足动作前置条件：{action.precondition}",
                evidence={"snapshot": _snapshot_evidence(before), "precondition": _check_evidence(precheck)},
            )

        candidate = choose_unique_candidate(self.locator.locate(before, action.locator), self.minimum_score)
        action_evidence = self.actuator.perform(action, candidate)
        self._ensure_not_aborted(action)
        if not action.wait_for_postcondition:
            return ActionRun(
                action_id=action.action_id,
                elapsed_ms=round((self.clock() - started_at) * 1000),
                evidence={
                    "before": _snapshot_evidence(before),
                    "precondition": _check_evidence(precheck),
                    "locator": _candidate_evidence(candidate),
                    "action": action_evidence,
                    "postchecks": [],
                },
            )
        postchecks: list[dict[str, Any]] = []
        deadline = started_at + action.timeout_seconds
        while True:
            self._ensure_not_aborted(action)
            after = self.observer.capture()
            postcheck = self.observer.check(after, action.postcondition)
            postchecks.append({"snapshot": _snapshot_evidence(after), "postcondition": _check_evidence(postcheck)})
            if postcheck.matched:
                return ActionRun(
                    action_id=action.action_id,
                    elapsed_ms=round((self.clock() - started_at) * 1000),
                    evidence={
                        "before": _snapshot_evidence(before),
                        "precondition": _check_evidence(precheck),
                        "locator": _candidate_evidence(candidate),
                        "action": action_evidence,
                        "postchecks": postchecks,
                    },
                )
            if self.clock() >= deadline:
                raise ExportAutomationError(
                    "POSTCONDITION_TIMEOUT",
                    f"动作后未在限定时间内满足页面条件：{action.postcondition}",
                    evidence={
                        "before": _snapshot_evidence(before),
                        "precondition": _check_evidence(precheck),
                        "locator": _candidate_evidence(candidate),
                        "action": action_evidence,
                        "postchecks": postchecks,
                    },
                )
            self.sleep(self.poll_interval_seconds)

    def _ensure_not_aborted(self, action: ExportAction) -> None:
        if self.abort_requested():
            raise ExportAutomationError(
                "PAUSE_REQUESTED",
                "检测到双击 Esc，已停止当前剪映动作",
                evidence={"action": action.action_id, "source": "double_escape"},
            )


def _snapshot_evidence(snapshot: PageSnapshot) -> dict[str, Any]:
    return {
        "window_handle": snapshot.window_handle,
        "captured_at": snapshot.captured_at,
        "screenshot_path": snapshot.screenshot_path,
        "metadata": snapshot.metadata,
    }


def _check_evidence(check: PageCheck) -> dict[str, Any]:
    return {"condition": check.condition, "matched": check.matched, "evidence": check.evidence}


def _candidate_evidence(candidate: LocatorCandidate) -> dict[str, Any]:
    return {
        "locator": candidate.locator,
        "x": candidate.x,
        "y": candidate.y,
        "score": candidate.score,
        "strategy": candidate.strategy,
        "evidence": candidate.evidence,
    }
