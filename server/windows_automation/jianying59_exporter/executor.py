"""One-draft orchestration around the upstream JianyingController flow.

The project deliberately owns state recovery, persistence, passive media
verification, and the optional post-verification cleanup only.  It does not
reimplement Jianying's home/editor/export-dialog workflow.
"""

from __future__ import annotations

import enum
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Protocol

from server.tool_resolver import ToolResolutionError, resolve_ffprobe


class ExportState(str, enum.Enum):
    PREFLIGHT = "PREFLIGHT"
    INSPECTING_STATE = "INSPECTING_STATE"
    RECOVERING_HOME = "RECOVERING_HOME"
    UPSTREAM_SUBMISSION = "UPSTREAM_SUBMISSION"
    SUBMITTED = "SUBMITTED"
    RELEASED = "RELEASED"
    MONITORING = "MONITORING"
    SUCCESS_PAGE_OBSERVED = "SUCCESS_PAGE_OBSERVED"
    MOVING_OUTPUT = "MOVING_OUTPUT"
    COMPLETED = "COMPLETED"
    CLEANING_SUCCESS_PAGE = "CLEANING_SUCCESS_PAGE"
    RETURNED_HOME = "RETURNED_HOME"
    FAILED = "FAILED"


class JianyingPage(str, enum.Enum):
    HOME = "HOME"
    EDIT = "EDIT"
    PARAMETER_DIALOG = "PARAMETER_DIALOG"
    EXPORTING = "EXPORTING"
    SUCCESS_PAGE = "SUCCESS_PAGE"
    UNKNOWN = "UNKNOWN"


class ExportFailure(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ExportRequest:
    draft_name: str
    output_directory: Path
    output_title: str
    expected_duration_seconds: float
    next_draft_available: bool = False
    allow_success_page_recovery: bool = False
    # Production exports leave Jianying's existing export settings untouched.
    # The flag remains for focused compatibility tests only.
    apply_export_parameters: bool = False
    # Temporary diagnostic switch for comparing UIA-only reads with OCR fallback.
    allow_parameter_ocr: bool = True
    # Retained only for focused compatibility tests when parameter selection
    # is explicitly enabled.
    force_parameter_selection: bool = False
    width: int = 1080
    height: int = 2400
    fps: float = 30.0
    codec: str = "h264"
    duration_tolerance_seconds: float = 1.0
    timeout_seconds: float = 900.0
    poll_interval_seconds: float = 1.0
    stable_samples: int = 2
    production_task: bool = False
    # Re-export still uses Jianying's default output path; this flag only
    # permits replacing an existing formal target after validation.
    allow_overwrite: bool = False
    trace_path: Path | None = None

    @property
    def expected_output_path(self) -> Path:
        return self.output_directory / f"{self.output_title}.mp4"

    @property
    def session_path(self) -> Path:
        return self.output_directory / f".{self.draft_name}.jianying59-session.json"

    def validate(self) -> None:
        if not self.production_task and not self.draft_name.startswith("__T039_"):
            raise ExportFailure("DRAFT_NOT_DISPOSABLE", "只允许导出以 __T039_ 开头的可丢弃测试草稿")
        if not self.output_title or any(char in self.output_title for char in '\\/:*?\"<>|'):
            raise ExportFailure("OUTPUT_TITLE_INVALID", "输出标题为空或包含 Windows 文件名非法字符")
        if self.expected_duration_seconds <= 0 or self.timeout_seconds <= 0:
            raise ExportFailure("REQUEST_INVALID", "期望时长和超时时间必须为正数")
        if self.poll_interval_seconds <= 0 or self.stable_samples < 2:
            raise ExportFailure("REQUEST_INVALID", "文件稳定性监视参数无效")
        if not self.output_directory.is_dir():
            raise ExportFailure("OUTPUT_DIRECTORY_MISSING", f"测试输出目录不存在：{self.output_directory}")
        if self.expected_output_path.exists() and not self.allow_overwrite:
            raise ExportFailure("OUTPUT_ALREADY_EXISTS", f"拒绝覆盖既有测试输出：{self.expected_output_path}")


@dataclass(frozen=True)
class PersistentSubmission:
    draft_name: str
    source_output_path: str
    expected_output_path: str
    submitted_at: float


@dataclass(frozen=True)
class StageEvent:
    state: ExportState
    action: str
    started_at: float
    elapsed_seconds: float
    detail: str = ""


@dataclass(frozen=True)
class MediaVerification:
    path: str
    bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    codec: str


@dataclass(frozen=True)
class ExportResult:
    ok: bool
    state: ExportState
    events: tuple[StageEvent, ...]
    output: MediaVerification | None = None
    failure_code: str = ""
    failure_detail: str = ""


class UpstreamJianyingDesktop(Protocol):
    """The only pre-submit GUI boundary: pyJianYingDraft upstream controller."""

    def preflight(self, request: ExportRequest) -> None: ...
    def begin_pre_submit(self) -> None: ...
    def release_pre_submit(self) -> None: ...
    def inspect_page(self) -> JianyingPage: ...
    def open_named_draft(self, draft_name: str) -> None: ...
    def return_edit_to_home(self) -> None: ...
    def close_unsubmitted_parameter_dialog(self) -> bool: ...
    def submit_with_upstream_controller(self, request: ExportRequest) -> PersistentSubmission: ...
    def observe_page_passively(self) -> JianyingPage: ...
    def close_success_and_return_home(self) -> None: ...


StatusSink = Callable[[StageEvent], None]
OperationSink = Callable[[dict[str, object]], None]


class SingleDraftExporter:
    """Serial, recovery-aware wrapper around one upstream controller export."""

    def __init__(self, desktop: UpstreamJianyingDesktop, *, ffprobe_path: str | None = None,
                 status_sink: StatusSink | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 operation_sink: OperationSink | None = None) -> None:
        self.desktop, self.status_sink = desktop, status_sink
        try:
            self.ffprobe_path = ffprobe_path or str(resolve_ffprobe())
        except ToolResolutionError:
            self.ffprobe_path = None
        self.clock, self.sleep, self.operation_sink = clock, sleep, operation_sink
        self._events: list[StageEvent] = []
        self._stage_started_at: float | None = None
        self._operation_started_at: dict[str, tuple[float, float]] = {}

    def _operation(self, operation_id: str, operation_name_zh: str, operation_type: str,
                   target: str, status: str, *, current_result: str = "") -> None:
        if self.operation_sink is None:
            return
        now = self.clock()
        if status == "STARTED" or operation_id not in self._operation_started_at:
            self._operation_started_at[operation_id] = (time.time(), now)
        started_wall, started = self._operation_started_at[operation_id]
        payload: dict[str, object] = {
            "operation_id": operation_id, "operation_name_zh": operation_name_zh,
            "operation_type": operation_type, "target": target, "status": status,
            "started_at": started_wall, "elapsed_ms": round(max(0.0, now - started) * 1000.0, 1),
            "current_result": current_result,
        }
        try:
            self.operation_sink(payload)
        except Exception:
            pass
        if status in {"DONE", "FOUND", "FAILED"}:
            self._operation_started_at.pop(operation_id, None)

    def prepare_and_open_named_draft(
        self, draft_name: str, *, page: JianyingPage | None = None, open_draft: bool = True,
    ) -> None:
        """Reuse the exporter's state recovery matrix and optionally stop in the editor."""
        page = page or self.desktop.inspect_page()
        if page == JianyingPage.EDIT:
            self.desktop.return_edit_to_home()
        elif page == JianyingPage.PARAMETER_DIALOG:
            if not self.desktop.close_unsubmitted_parameter_dialog():
                raise ExportFailure("PARAMETER_DIALOG_RECOVERY_UNSUPPORTED", "未提交参数窗没有实测唯一关闭动作；拒绝坐标猜点")
            self.desktop.return_edit_to_home()
        elif page == JianyingPage.SUCCESS_PAGE:
            self.desktop.close_success_and_return_home()
        elif page == JianyingPage.EXPORTING:
            raise ExportFailure("EXPORT_IN_PROGRESS", "剪映当前仍在导出，拒绝打开草稿")
        elif page != JianyingPage.HOME:
            raise ExportFailure("JIANYING_PAGE_UNKNOWN", "5.9 UIA 无法唯一识别当前页面；不猜点击")
        if open_draft:
            self.desktop.open_named_draft(draft_name)

    def execute(self, request: ExportRequest) -> ExportResult:
        self._events, self._stage_started_at = [], None
        self._operation_started_at = {}
        try:
            request.validate()
            if not self.ffprobe_path:
                raise ExportFailure("FFPROBE_MISSING", "本机未找到 ffprobe，不能把导出标记为完成")
            self._stage(ExportState.PREFLIGHT, "验证可丢弃草稿、测试目录与媒体校验工具")
            self.desktop.preflight(request)
            # Make the first visible action match the desktop contract.  Page
            # recovery can be slow on a retained success screen, but it must
            # happen after the one foreground handoff, not invisibly before it.
            self.desktop.begin_pre_submit()
            self._stage(ExportState.INSPECTING_STATE, "以 5.9 UIA 事实识别当前剪映页面")
            self._operation("INSPECT_PAGE", "识别当前剪映页面", "ACTION", "剪映当前页面", "STARTED")
            page = self.desktop.inspect_page()
            self._operation("INSPECT_PAGE", "识别当前剪映页面", "ACTION", "剪映当前页面", "DONE", current_result=page.value)
            record = _load_submission(request.session_path)
            submission = self._recover_or_submit(request, page, record)
            self._stage(ExportState.RELEASED, "最终导出已确认；上游前台保护已释放")
            self._stage(ExportState.MONITORING, "被动观察成功页与已绑定源 MP4，不操作剪映")
            source = Path(submission.source_output_path)
            verification, success_seen = self._wait_for_media(source, request)
            if success_seen:
                self._stage(ExportState.SUCCESS_PAGE_OBSERVED, "仅观察到当前持久化会话的剪映成功页")
            if _normalise(source) != _normalise(request.expected_output_path):
                self._stage(ExportState.MOVING_OUTPUT, "源 MP4 已验收；移动至规则归档路径")
                self._operation("MOVE_OUTPUT", "整理到正式输出路径", "ACTION", str(request.expected_output_path), "STARTED")
                self._move_verified_output(source, request.expected_output_path, allow_overwrite=request.allow_overwrite)
                self._operation("MOVE_OUTPUT", "整理到正式输出路径", "ACTION", str(request.expected_output_path), "DONE", current_result="输出文件已整理")
                verification, _ = self._wait_for_media(request.expected_output_path, request, observe_page=False)
            self._operation("MARK_COMPLETE", "更新任务完成状态", "ACTION", "导出任务状态", "STARTED")
            self._stage(ExportState.COMPLETED, "MP4 已稳定且 ffprobe 验收通过")
            self._operation("MARK_COMPLETE", "更新任务完成状态", "ACTION", "导出任务状态", "DONE", current_result="任务已完成")
            if request.next_draft_available and self.desktop.observe_page_passively() == JianyingPage.SUCCESS_PAGE:
                self._stage(ExportState.CLEANING_SUCCESS_PAGE, "媒体已验收且存在下一份，关闭当前成功页并回首页")
                self._operation("CLOSE_SUCCESS", "关闭导出成功页", "ACTION", "导出成功页关闭按钮", "STARTED")
                self._operation("RETURN_HOME", "返回剪映首页", "ACTION", "剪映首页", "STARTED")
                self.desktop.close_success_and_return_home()
                self._operation("CLOSE_SUCCESS", "关闭导出成功页", "ACTION", "导出成功页关闭按钮", "DONE", current_result="成功页已关闭")
                self._stage(ExportState.RETURNED_HOME, "成功页已关闭并返回首页；尚未打开下一份草稿")
                self._operation("RETURN_HOME", "返回剪映首页", "ACTION", "剪映首页", "DONE", current_result="已返回首页")
            _clear_submission(request.session_path)
            self._seal_current_stage()
            return ExportResult(True, self._events[-1].state, tuple(self._events), verification)
        except ExportFailure as exc:
            self._stage(ExportState.FAILED, "停止本次单份导出", f"{exc.code}: {exc.detail}")
            self._seal_current_stage()
            return ExportResult(False, ExportState.FAILED, tuple(self._events), failure_code=exc.code, failure_detail=exc.detail)
        except Exception as exc:
            self._stage(ExportState.FAILED, "停止本次单份导出", f"UNEXPECTED_FAILURE: {exc}")
            self._seal_current_stage()
            return ExportResult(False, ExportState.FAILED, tuple(self._events), failure_code="UNEXPECTED_FAILURE", failure_detail=str(exc))
        finally:
            self.desktop.release_pre_submit()

    def _recover_or_submit(self, request: ExportRequest, page: JianyingPage,
                           record: PersistentSubmission | None) -> PersistentSubmission:
        if page in {JianyingPage.HOME, JianyingPage.EDIT, JianyingPage.PARAMETER_DIALOG}:
            if page != JianyingPage.HOME:
                self._stage(ExportState.RECOVERING_HOME, "按正式状态恢复规则返回剪映首页")
            self.prepare_and_open_named_draft(request.draft_name, page=page, open_draft=False)
            return self._submit_new(request)
        if page == JianyingPage.SUCCESS_PAGE and record is None:
            self._stage(ExportState.CLEANING_SUCCESS_PAGE, "按正式状态恢复规则关闭成功页并回首页")
            self.prepare_and_open_named_draft(request.draft_name, page=page, open_draft=False)
            self._stage(ExportState.RETURNED_HOME, "剪映已回到首页，开始当前任务")
            return self._submit_new(request)
        if page in {JianyingPage.EXPORTING, JianyingPage.SUCCESS_PAGE}:
            if record is not None:
                return record
            if page == JianyingPage.EXPORTING:
                self._stage(ExportState.MONITORING, "剪映已有导出；释放桌面并等待它结束")
                self._wait_for_external_export_to_finish(request)
            self._stage(ExportState.CLEANING_SUCCESS_PAGE, "当前不是导出中，关闭成功页并回首页")
            self.desktop.close_success_and_return_home()
            self._stage(ExportState.RETURNED_HOME, "剪映已回到首页，开始当前任务")
            return self._submit_new(request)
        raise ExportFailure("JIANYING_PAGE_UNKNOWN", "5.9 UIA 无法唯一识别当前页面；不猜点击")

    def _wait_for_external_export_to_finish(self, request: ExportRequest) -> None:
        deadline = self.clock() + request.timeout_seconds
        while self.desktop.observe_page_passively() == JianyingPage.EXPORTING:
            if self.clock() >= deadline:
                raise ExportFailure("EXTERNAL_EXPORT_TIMEOUT", "已有剪映导出未在限定时间内结束")
            self.sleep(request.poll_interval_seconds)

    def _submit_new(self, request: ExportRequest) -> PersistentSubmission:
        self._stage(ExportState.UPSTREAM_SUBMISSION, "按 5.9 控件条件提交剪映导出")
        submission = self.desktop.submit_with_upstream_controller(request)
        if submission.draft_name != request.draft_name or _normalise(Path(submission.expected_output_path)) != _normalise(request.expected_output_path):
            raise ExportFailure("SUBMISSION_BINDING_MISMATCH", "上游提交回执未绑定当前草稿和独立测试输出")
        _save_submission(request.session_path, submission)
        self._stage(ExportState.SUBMITTED, "上游最终导出已确认被剪映接受")
        return submission

    def _wait_for_media(self, path: Path, request: ExportRequest, *, observe_page: bool = True) -> tuple[MediaVerification, bool]:
        deadline, previous, stable, success_seen = self.clock() + request.timeout_seconds, None, 0, False
        self._operation("WAIT_MP4_APPEAR", "等待 MP4 文件出现", "WAIT", path.name, "STARTED")
        while True:
            if observe_page:
                success_seen = self.desktop.observe_page_passively() == JianyingPage.SUCCESS_PAGE or success_seen
            try:
                stat = path.stat(); signature = (stat.st_size, stat.st_mtime_ns) if stat.st_size > 0 else None
            except FileNotFoundError:
                signature = None
            was_present = previous is not None
            stable = stable + 1 if signature and signature == previous else (1 if signature else 0)
            previous = signature
            if signature is None:
                self._operation("WAIT_MP4_APPEAR", "等待 MP4 文件出现", "WAIT", path.name, "WAITING", current_result="尚未出现")
            else:
                if not was_present:
                    self._operation("WAIT_MP4_APPEAR", "等待 MP4 文件出现", "WAIT", path.name, "FOUND", current_result="文件已出现")
                if "WAIT_MP4_STABLE" not in self._operation_started_at:
                    self._operation("WAIT_MP4_STABLE", "等待 MP4 文件稳定", "WAIT", path.name, "STARTED")
                self._operation("WAIT_MP4_STABLE", "等待 MP4 文件稳定", "WAIT", path.name, "DONE" if stable >= request.stable_samples else "WAITING", current_result=f"连续稳定样本 {stable}/{request.stable_samples}")
            if stable >= request.stable_samples:
                self._operation("RUN_FFPROBE", "执行 ffprobe", "ACTION", path.name, "STARTED")
                self._operation("VERIFY_MP4", "验证视频", "ACTION", path.name, "STARTED")
                verification = self._verify_media(path, request)
                self._operation("RUN_FFPROBE", "执行 ffprobe", "ACTION", path.name, "DONE", current_result="媒体元数据已读取")
                self._operation("VERIFY_MP4", "验证视频", "ACTION", path.name, "DONE", current_result="视频符合媒体要求")
                return verification, success_seen
            if self.clock() >= deadline:
                raise ExportFailure("OUTPUT_STABILITY_TIMEOUT", "目标 MP4 未在限定时间内稳定并通过验收")
            self.sleep(request.poll_interval_seconds)

    def _verify_media(self, path: Path, request: ExportRequest) -> MediaVerification:
        command = [str(self.ffprobe_path), "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate", "-of", "json", str(path)]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            payload = json.loads(completed.stdout or "{}")
        except (OSError, ValueError) as exc:
            raise ExportFailure("FFPROBE_FAILED", f"ffprobe 无法读取输出 MP4：{exc}") from exc
        if completed.returncode:
            raise ExportFailure("FFPROBE_FAILED", completed.stderr.strip()[-1000:] or "ffprobe 校验失败")
        video = next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), None)
        if not isinstance(video, dict):
            raise ExportFailure("VIDEO_STREAM_MISSING", "输出文件没有视频流")
        result = MediaVerification(str(path), path.stat().st_size, float(payload.get("format", {}).get("duration") or 0), int(video.get("width") or 0), int(video.get("height") or 0), _rate(video.get("avg_frame_rate") or video.get("r_frame_rate")), str(video.get("codec_name") or ""))
        if result.bytes <= 0 or result.width != request.width or result.height != request.height or result.codec.casefold() != request.codec.casefold() or abs(result.fps - request.fps) > .01 or abs(result.duration_seconds - request.expected_duration_seconds) > request.duration_tolerance_seconds:
            raise ExportFailure("MEDIA_CONTRACT_FAILED", f"ffprobe 结果不符合合同：{result.width}x{result.height}, {result.fps:.3f}fps, {result.codec}, {result.duration_seconds:.3f}s")
        return result

    @staticmethod
    def _move_verified_output(source: Path, target: Path, *, allow_overwrite: bool = False) -> None:
        """Keep exactly one verified MP4 after Jianying's native export."""
        if target.exists():
            if not allow_overwrite:
                raise ExportFailure("OUTPUT_ALREADY_EXISTS", f"拒绝覆盖既有导出文件：{target}")
            try:
                os.replace(source, target)
                return
            except OSError as exc:
                raise ExportFailure("OUTPUT_REPLACE_FAILED", f"已验收 MP4 无法替换正式视频：{exc}") from exc
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            raise ExportFailure("OUTPUT_MOVE_FAILED", f"已验收 MP4 无法移动到规则路径：{exc}") from exc

    def _stage(self, state: ExportState, action: str, detail: str = "") -> None:
        self._seal_current_stage(); event = StageEvent(state, action, self.clock(), 0.0, detail)
        self._events.append(event); self._stage_started_at = event.started_at
        if self.status_sink: self.status_sink(event)

    def _seal_current_stage(self) -> None:
        if self._events and self._stage_started_at is not None:
            self._events[-1] = replace(self._events[-1], elapsed_seconds=max(0.0, self.clock() - self._stage_started_at)); self._stage_started_at = None


def _load_submission(path: Path) -> PersistentSubmission | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8")); return PersistentSubmission(**data)
    except FileNotFoundError:
        return None
    except (OSError, TypeError, ValueError) as exc:
        raise ExportFailure("SESSION_RECORD_INVALID", f"当前持久化导出会话记录不可读：{exc}") from exc


def _save_submission(path: Path, submission: PersistentSubmission) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(submission), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _clear_submission(path: Path) -> None:
    try: path.unlink()
    except FileNotFoundError: pass


def _normalise(path: Path) -> str: return str(path.resolve()).casefold()


def _rate(value: object) -> float:
    try:
        text = str(value or "0")
        if "/" in text:
            numerator, denominator = text.split("/", 1); return float(numerator) / float(denominator) if float(denominator) else 0.0
        return float(text)
    except ValueError: return 0.0
