"""V2-owned real Jianying export runtime.

The V2 runner owns attempts, deadlines, aborts, media acceptance and file
finalising. Its Windows input lease, process discovery and 5.9 UIA controller
implementation are supplied by V2's internal low-level runtime.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from server.tool_resolver import ToolResolutionError, resolve_ffprobe
from server.runtime_process import no_window_kwargs


class V2ExportFailure(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


def _is_retryable_home_search_failure(exc: Exception) -> bool:
    """Only retry the harmless QML search-refresh gap before any draft click."""
    return (
        getattr(exc, "code", "") == "UI_CONDITION_TIMEOUT"
        and "搜索后的唯一完整草稿名称" in str(exc)
    )


def _is_retryable_draft_click_failure(exc: Exception) -> bool:
    """A card click may be swallowed while Jianying is still loading.

    This is safe to retry only after V2 proves that Jianying is still on its
    homepage.  If it has switched page, guessing would risk opening or
    operating a different draft.
    """
    return (
        getattr(exc, "code", "") == "UI_CONDITION_TIMEOUT"
        and "编辑页导出按钮" in str(exc)
    )


FINAL_EXPORT_ACCEPTANCE_SECONDS = 1.5
FINAL_EXPORT_CLICK_MAX_ATTEMPTS = 3


def _automation_imports() -> tuple[Any, Any, Any, Any, Any]:
    """Load V2-owned Windows and Jianying low-level automation primitives."""
    try:
        from server.windows_automation.jianying_adapter import WindowsInputLeaseAdapter, foreground_jianying_window
        from server.windows_automation.jianying_runtime import WindowsJianyingRuntime
        from server.windows_automation.jianying59_exporter.executor import ExportFailure, ExportRequest, JianyingPage
        from server.windows_automation.jianying59_exporter.upstream_adapter import PyJianyingUpstreamAdapter
    except ImportError as exc:
        raise V2ExportFailure("WINDOWS_AUTOMATION_UNAVAILABLE", f"V2 内置剪映低层组件不可导入：{exc}") from exc
    return WindowsInputLeaseAdapter, foreground_jianying_window, WindowsJianyingRuntime, (ExportFailure, ExportRequest, JianyingPage), PyJianyingUpstreamAdapter


class WindowsInputLease:
    """Real exclusive keyboard/mouse lease with V2 abort semantics."""
    def __init__(self, *, maximum_seconds: float) -> None:
        self.maximum_seconds = maximum_seconds
        self._expires_at = time.monotonic() + maximum_seconds
        self._adapter: Any | None = None
        self._attempt_id = ""
        self._lock = threading.RLock()
        self._abort_requested = threading.Event()
        self._stop_abort_listener = threading.Event()
        self._lease_generation = 0

    def acquire(self, attempt_id: str) -> None:
        with self._lock:
            if self._adapter is not None:
                if self._attempt_id == attempt_id:
                    return
                raise V2ExportFailure("INPUT_LEASE_CONFLICT", "已有其他 V2 导出尝试持有键鼠")
            adapter_type, _foreground, _runtime, _types, _upstream = _automation_imports()
            self._adapter, self._attempt_id = adapter_type(), attempt_id
            self._abort_requested.clear()
            self._stop_abort_listener = threading.Event()
            self._lease_generation += 1
            generation = self._lease_generation
        try:
            assert self._adapter is not None
            self._adapter.acquire(attempt_id, maximum_seconds=self.maximum_seconds)
        except Exception as exc:
            with self._lock:
                self._adapter, self._attempt_id = None, ""
                self._stop_abort_listener.set()
            raise V2ExportFailure("INPUT_LEASE_UNAVAILABLE", f"无法接管 Windows 键鼠：{exc}") from exc
        threading.Thread(
            target=self._watch_double_escape,
            args=(attempt_id, generation, self._stop_abort_listener),
            name="v2-double-escape-release",
            daemon=True,
        ).start()

    def release(self, attempt_id: str) -> None:
        with self._lock:
            if self._adapter is None:
                return
            if self._attempt_id != attempt_id:
                raise V2ExportFailure("INPUT_LEASE_OWNER_MISMATCH", "键鼠接管所有者不匹配")
            adapter, self._adapter, self._attempt_id = self._adapter, None, ""
            self._stop_abort_listener.set()
        try:
            adapter.release(attempt_id)
        except Exception:
            # Release must be best effort on every terminal path.
            try:
                adapter.release_all()
            except Exception:
                pass

    def aborted(self, attempt_id: str) -> bool:
        if self._abort_requested.is_set():
            return True
        return bool(self._adapter is not None and self._attempt_id == attempt_id and self._adapter.pause_requested(attempt_id))

    def require_active(self, attempt_id: str) -> None:
        # The V2 listener releases Windows input as soon as it observes the
        # second Esc.  Keep this durable flag separate from adapter activity:
        # after an immediate release, adapter.is_active() is intentionally
        # false and must not turn a user abort into INPUT_LEASE_LOST.
        if self._abort_requested.is_set():
            self.release(attempt_id)
            raise V2ExportFailure("USER_DOUBLE_ESC_ABORT", "用户双 ESC 紧急终止")
        # The low-level watchdog releases the same input lease when its safety limit
        # is reached.  That is a timeout, not evidence that the user pressed
        # Esc; check it first so it can never be recorded as double-Esc.
        if time.monotonic() >= self._expires_at:
            self.release(attempt_id)
            raise V2ExportFailure("INPUT_LEASE_TIMEOUT", "导出前台操作超过本次允许时间，已安全释放键鼠")
        if self.aborted(attempt_id):
            self.release(attempt_id)
            raise V2ExportFailure("USER_DOUBLE_ESC_ABORT", "用户双 ESC 紧急终止")
        if self._adapter is None or self._attempt_id != attempt_id or not self._adapter.is_active(attempt_id):
            raise V2ExportFailure("INPUT_LEASE_LOST", "键鼠接管已丢失，停止继续操作")

    def _watch_double_escape(self, attempt_id: str, generation: int, stop_listener: threading.Event) -> None:
        """Release Windows input immediately; task state closes on the worker thread."""
        if os.name != "nt":
            return
        was_down = False
        first_press_at: float | None = None
        while not stop_listener.wait(0.02):
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
            except Exception:
                return
            if down and not was_down:
                now = time.monotonic()
                if first_press_at is not None and now - first_press_at <= 0.75:
                    self._emergency_abort(attempt_id, generation)
                    return
                first_press_at = now
            was_down = down

    def _emergency_abort(self, attempt_id: str, generation: int) -> None:
        """Called by the key listener, before a potentially blocked UIA call returns."""
        with self._lock:
            if self._attempt_id != attempt_id or self._lease_generation != generation:
                return
            self._abort_requested.set()
        # Do not wait for the UIA worker to reach require_active(): users need
        # keyboard and mouse control back even while that call is blocked.
        self.release(attempt_id)


class _V2ForegroundGuard:
    """Adapter protocol used by the low-level UIA code, backed by the V2 lease."""
    def __init__(self, lease: WindowsInputLease, attempt_id: str) -> None:
        self.lease, self.attempt_id = lease, attempt_id

    def acquire(self) -> None:
        self.lease.require_active(self.attempt_id)
        _lease, foreground, _runtime, _types, _upstream = _automation_imports()
        try:
            foreground(maximize=True)
        except Exception as exc:
            raise V2ExportFailure("JIANYING_FOREGROUND_FAILED", f"剪映未能取得前台焦点：{exc}") from exc

    def ensure(self) -> None:
        self.lease.require_active(self.attempt_id)

    def release(self) -> None:
        # V2 owns the one continuous lease and releases only at business edges.
        return


@dataclass(frozen=True)
class Submission:
    source_path: Path
    baseline: dict[str, int | bool]


class Jianying59Bridge:
    """V2 facade over proven 5.9 UIA reads/actions; it has no external queue state."""
    def __init__(self, lease: WindowsInputLease, attempt_id: str, *, executable: str = "", debug_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.lease, self.attempt_id, self.executable, self.debug_sink = lease, attempt_id, executable, debug_sink
        self._adapter: Any | None = None
        self._prepared_draft: tuple[str, Any, Any, Any] | None = None

    def ensure_started(self) -> None:
        _lease, _foreground, runtime_type, types, upstream = _automation_imports()
        config = SimpleNamespace(jianying_executable=Path(self.executable) if self.executable else None)
        try:
            runtime_type().ensure_started(config)
        except Exception as exc:
            raise V2ExportFailure("JIANYING_START_FAILED", str(exc)) from exc
        self._adapter = upstream(foreground_guard_factory=lambda: _V2ForegroundGuard(self.lease, self.attempt_id), trace_sink=self.debug_sink, operation_sink=self.debug_sink)
        try:
            # The adapter's preflight only binds installed UIA dependencies;
            # it does not click Jianying or change its export settings.
            self._adapter.preflight(SimpleNamespace(output_directory=Path.cwd(), apply_export_parameters=False, allow_parameter_ocr=False))
        except Exception as exc:
            raise V2ExportFailure(getattr(exc, "code", "JIANYING_PREFLIGHT_FAILED"), str(exc)) from exc

    def _desktop(self) -> Any:
        if self._adapter is None:
            raise V2ExportFailure("JIANYING_NOT_READY", "剪映连接尚未建立")
        self.lease.require_active(self.attempt_id)
        return self._adapter

    def _interruptible_sleep(self, seconds: float) -> None:
        """Keep V2's double-Esc contract alive inside every UIA wait loop."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self.lease.require_active(self.attempt_id)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            # UIA waits normally sleep for 150ms.  A shorter slice makes the
            # emergency stop responsive without increasing UIA polling.
            time.sleep(min(0.05, remaining))

    def _open_named_draft(self, desktop: Any, draft_name: str) -> tuple[Any, Any, Any]:
        """Open once and retain the confirmed export-button handle for V2."""
        from server.windows_automation.jianying59_exporter.upstream_adapter import PassiveUpstreamController
        from pyJianYingDraft.jianying_controller import ControlFinder

        session = PassiveUpstreamController(
            desktop._controller_type,
            uia=desktop._uia,
            sleep=self._interruptible_sleep,
            monotonic=desktop._monotonic,
            foreground_guard=_V2ForegroundGuard(self.lease, self.attempt_id),
            trace_sink=self.debug_sink,
            operation_sink=self.debug_sink,
        )
        session._foreground_guard.acquire()
        controller = session._controller_type()
        export_button = session._open_draft_until_editor(controller, draft_name, ControlFinder)
        return session, controller, export_button

    def _take_prepared_draft(self, draft_name: str) -> tuple[Any, Any, Any] | None:
        """Return the exact editor/button confirmed while opening this draft.

        Both template and finished-video drafts use the same Jianying editor.
        Throwing the finished-video handle away forced V2 to bind MainWindow a
        second time immediately after it appeared, which is the source of the
        visible ten-second pause before the top-right export click.
        """
        prepared, self._prepared_draft = self._prepared_draft, None
        if prepared is None or prepared[0] != draft_name:
            return None
        return prepared[1:]

    def recover_and_open(self, draft_name: str) -> None:
        _lease, _foreground, _runtime, types, _upstream = _automation_imports()
        _failure, _request, page_type = types
        desktop = self._desktop()
        self._prepared_draft = None
        try:
            page = self._fast_inspect_page(desktop, page_type)
            # The low-level helper is only the page/draft UIA primitive. V2
            # chooses when it is allowed and owns export recovery/session policy.
            if page == page_type.EDIT:
                desktop.return_edit_to_home()
            elif page == page_type.PARAMETER_DIALOG:
                if not desktop.close_unsubmitted_parameter_dialog():
                    raise V2ExportFailure("PARAMETER_DIALOG_RECOVERY_UNSUPPORTED", "无法可靠关闭未提交的导出参数窗")
                desktop.return_edit_to_home()
            elif page == page_type.SUCCESS_PAGE:
                desktop.close_success_and_return_home()
            elif page == page_type.EXPORTING:
                raise V2ExportFailure("EXPORT_IN_PROGRESS", "剪映当前正在导出，不能领取新任务")
            elif page != page_type.HOME:
                raise V2ExportFailure("JIANYING_PAGE_UNKNOWN", "无法唯一识别剪映当前页面")
            self.lease.require_active(self.attempt_id)
            try:
                prepared = self._open_named_draft(desktop, draft_name)
            except Exception as exc:
                # After the homepage search value is set, Jianying 5.9 can
                # take a short time to rebuild its card list.  The first
                # lookup may therefore miss a draft that exists on disk.  A
                # single fresh-home retry is safe: no card was clicked and no
                # export dialog was opened on the failed lookup.
                if _is_retryable_home_search_failure(exc):
                    self.lease.require_active(self.attempt_id)
                    time.sleep(1.0)
                    if self._fast_inspect_page(desktop, page_type) != page_type.HOME:
                        raise V2ExportFailure("HOME_STATE_UNCONFIRMED", "草稿搜索刷新后剪映未回到可确认首页，已停止避免误点") from exc
                    prepared = self._open_named_draft(desktop, draft_name)
                elif _is_retryable_draft_click_failure(exc):
                    # The card was found and clicked, but no editor appeared.
                    # Re-checking the homepage first distinguishes a swallowed
                    # click from a real page transition; only the former gets
                    # one fresh foreground handoff and one retry.
                    self.lease.require_active(self.attempt_id)
                    if self._fast_inspect_page(desktop, page_type) != page_type.HOME:
                        raise V2ExportFailure("DRAFT_OPEN_STATE_UNCONFIRMED", "草稿点击后剪映页面状态无法确认，已停止避免重复打开") from exc
                    prepared = self._open_named_draft(desktop, draft_name)
                else:
                    raise
            self._prepared_draft = (draft_name, *prepared)
        except V2ExportFailure:
            raise
        except Exception as exc:
            raise V2ExportFailure(getattr(exc, "code", "JIANYING_UIA_FAILED"), str(exc)) from exc

    @staticmethod
    def _fast_inspect_page(desktop: Any, page_type: Any) -> Any:
        """Use the internal direct-window strategy, never a UIA root walk.

        The old public ``inspect_page`` walks the desktop then a depth-5
        subtree, which can stall for roughly ten seconds while QML is alive.
        V2 only needs the three known direct selectors before opening a draft.
        """
        uia = desktop._uia
        window = getattr(uia, "WindowControl", None)
        if not callable(window):
            return desktop.inspect_page()  # focused test doubles only
        editor = window(searchDepth=1, searchInterval=0, Name="剪映专业版", AutomationId="MainWindow")
        editor_exists = bool(editor is not None and editor.Exists(0))
        if editor_exists:
            # For the HomeWindow -> MainWindow handoff:
            # querying HomeWindow while Jianying is destroying it can block for
            # about ten seconds even though the editor's Export button is
            # already visible.  MainWindow is sufficient once it exists.
            container = editor.Control(searchDepth=1, searchInterval=0, AutomationId="ExportWindow_Container")
            if container is None or not container.Exists(0):
                return page_type.EDIT
            description = lambda value: (lambda control, _depth: str(control.GetPropertyValue(30159) or "") == value)
            final = container.TextControl(searchDepth=2, searchInterval=0, Compare=description("ExportOkBtn"))
            success = container.TextControl(searchDepth=2, searchInterval=0, Compare=description("ExportSucceedCloseBtn"))
            if success is not None and success.Exists(0):
                return page_type.SUCCESS_PAGE
            return page_type.PARAMETER_DIALOG if final is not None and final.Exists(0) else page_type.EXPORTING
        home = window(searchDepth=1, searchInterval=0, Name="剪映专业版", AutomationId="HomeWindow")
        return page_type.HOME if home is not None and home.Exists(0) else page_type.UNKNOWN

    def submit(self, *, draft_name: str, target_path: Path, expected_duration: float, subject_type: str,
               on_baseline: Callable[[Path, dict[str, int | bool]], None] | None = None) -> Submission:
        _lease, _foreground, _runtime, types, _upstream = _automation_imports()
        _failure, _request_type, _page = types
        desktop = self._desktop()
        try:
            # Do not use the low-level SingleDraftExporter submission wrapper here: V2
            # needs its source-file baseline *before* the final click.  These
            # are the same proved 5.9 UIA selectors, split at that safe edge.
            from server.windows_automation.jianying59_exporter.upstream_adapter import PassiveUpstreamController, _SubmissionAccepted
            from pyJianYingDraft.jianying_controller import ControlFinder
            prepared = self._take_prepared_draft(draft_name)
            if prepared is not None:
                # The low-level controller opens the draft, confirms this exact control, then
                # clicks it in the same UI sequence.  Recreating a controller
                # here was V2-only duplicate waiting while the button was
                # already visible on screen.
                session, controller, export_button = prepared
            else:
                session = PassiveUpstreamController(desktop._controller_type, uia=desktop._uia, sleep=self._interruptible_sleep,
                                                    monotonic=desktop._monotonic, foreground_guard=_V2ForegroundGuard(self.lease, self.attempt_id),
                                                    trace_sink=self.debug_sink, operation_sink=self.debug_sink)
                session._foreground_guard.acquire()
                controller, export_button = session._controller_type(), None
            # Match the current fast path exactly: click the already-confirmed
            # editor button, then use the returned ExportWindow as the root
            # for path and final-button lookup. V2 does not alter export
            # parameters here, so waiting for a resolution field is wrong.
            export_dialog = session._open_export_dialog(
                controller, ControlFinder, export_button=export_button, wait_for_ready=False
            )
            if export_dialog is not None:
                controller.app = export_dialog
            path_anchor, final_button = self._wait_for_export_submission_controls(session, controller, ControlFinder)
            session._capture_native_output_path(path_anchor)
            raw_source = str(session.source_output_path or "").strip()
            source = Path(raw_source).expanduser()
            if not raw_source or not source.is_absolute():
                raise V2ExportFailure("UPSTREAM_SOURCE_PATH_UNREADABLE", "剪映未返回绝对原始输出路径")
            baseline = file_baseline(source)
            if on_baseline is not None:
                on_baseline(source.resolve(), baseline)
            self._submit_final_export_with_receipt(session, controller, ControlFinder, final_button)
            return Submission(source.resolve(), baseline)
        except V2ExportFailure:
            raise
        except Exception as exc:
            raise V2ExportFailure(getattr(exc, "code", "SUBMISSION_UNCONFIRMED"), str(exc)) from exc

    def _wait_for_export_submission_controls(self, session: Any, controller: Any, finder: Any) -> tuple[Any, Any]:
        """Read path and final button from the same live parameter panel.

        The former V2 flow waited up to ten seconds for ExportPath and then
        started another independent ten-second wait for ExportOkBtn.  During a
        QML panel transition that also kept querying the original container,
        even when the visible parameter page was already ready.  Both facts
        are required before a safe final click, so wait for them together and
        periodically bind the currently visible ExportWindow_Container again.
        """
        deadline = time.monotonic() + 10.0
        last_rebind_at = 0.0
        while True:
            self.lease.require_active(self.attempt_id)
            try:
                path_anchor = controller.app.TextControl(
                    searchDepth=2, Compare=finder.desc_matcher("ExportPath")
                )
                final_button = controller.app.TextControl(
                    searchDepth=2, Compare=finder.desc_matcher("ExportOkBtn", exact=True)
                )
                if bool(path_anchor.Exists(0)) and bool(final_button.Exists(0)):
                    session._trace("导出参数页关键控件已就绪", stage="WAIT_EXPORT_SUBMISSION_CONTROLS", result="OK")
                    return path_anchor, final_button
            except Exception:
                # QML can reject a child query while its parameter sheet is
                # being attached. The fresh-container pass below is the safe
                # recovery; no click is performed here.
                pass

            now = time.monotonic()
            if now - last_rebind_at >= 0.5:
                last_rebind_at = now
                try:
                    raw_root = getattr(session, "_raw_app", None)
                    container = session._find_export_container(raw_root) if raw_root is not None else None
                    if container is not None and bool(container.Exists(0)):
                        controller.app = container
                except Exception:
                    pass
            if now >= deadline:
                raise V2ExportFailure("EXPORT_SUBMISSION_CONTROLS_TIMEOUT", "导出参数页已打开，但 10 秒内未同时读到剪映输出路径和最终导出按钮")
            self._interruptible_sleep(0.15)

    def _submit_final_export_with_receipt(self, session: Any, controller: Any, finder: Any, final_button: Any) -> None:
        """Click final export only when a preceding click has demonstrably failed.

        A visible button is not proof that its first click was received: QML
        occasionally swallows a click while the parameter panel is finishing
        its animation.  Conversely, retrying after Jianying accepted the
        export would be unsafe.  Therefore each click gets a short receipt
        window; a retry is permitted solely while the same final button is
        still present.  The retry re-foregrounds Jianying and re-finds the
        control instead of using a stale UIA object.
        """
        for click_number in range(1, FINAL_EXPORT_CLICK_MAX_ATTEMPTS + 1):
            self.lease.require_active(self.attempt_id)
            try:
                # Do not call the low-level proxy here: it releases its foreground
                # guard and waits 15 seconds after the first click, which
                # prevents V2 from recovering a swallowed QML click.
                raw_button = getattr(final_button, "_raw", final_button)
                raw_button.Click(simulateMove=False)
            except Exception as exc:
                raise V2ExportFailure("FINAL_EXPORT_CLICK_FAILED", f"最终导出按钮点击失败：{exc}") from exc

            deadline = time.monotonic() + FINAL_EXPORT_ACCEPTANCE_SECONDS
            while time.monotonic() < deadline:
                self._interruptible_sleep(0.15)
                if not session._final_button_exists():
                    session._operation("CLICK_EXPORT_OK", "点击最终「导出」", "ACTION", "ExportOkBtn（最终导出按钮）", "DONE", current_result=f"第 {click_number} 次点击已获剪映接受")
                    session.release_pre_submit()
                    return

            if click_number == FINAL_EXPORT_CLICK_MAX_ATTEMPTS:
                break
            session._trace("最终导出按钮仍在，重新置前后再次点击", f"第 {click_number + 1}/{FINAL_EXPORT_CLICK_MAX_ATTEMPTS} 次", stage="SUBMIT_EXPORT", waiting_for="ExportOkBtn")
            # A notification or another application may have covered the QML
            # panel.  Re-foreground before locating the next click target.
            session._foreground_guard.acquire()
            final_button = session._wait_for_control(
                controller, "最终导出按钮",
                lambda app: app.TextControl(searchDepth=2, Compare=finder.desc_matcher("ExportOkBtn", exact=True)),
                timeout_seconds=2, refresh_window=False,
            )
        raise V2ExportFailure("SUBMISSION_UNCONFIRMED", "最终导出按钮连续点击后仍未得到剪映接受确认；已停止避免重复提交")


def file_baseline(path: Path) -> dict[str, int | bool]:
    try:
        stat = path.stat()
        return {"exists": True, "size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    except FileNotFoundError:
        return {"exists": False, "size": 0, "mtime_ns": 0}


def source_is_new(path: Path, baseline: dict[str, Any]) -> bool:
    current = file_baseline(path)
    return bool(current["exists"] and (not baseline.get("exists") or current["size"] != baseline.get("size") or current["mtime_ns"] != baseline.get("mtime_ns")))


@dataclass(frozen=True)
class MediaInfo:
    path: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    codec: str


def _rate(value: object) -> float:
    text = str(value or "0")
    try:
        if "/" in text:
            left, right = text.split("/", 1)
            return float(left) / float(right) if float(right) else 0.0
        return float(text)
    except ValueError:
        return 0.0


def verify_media(path: Path, *, expected_duration: float, width: int = 1080, height: int = 2400, fps: float = 30.0, ffprobe_path: str | Path | None = None) -> MediaInfo:
    """Accept an exported video by its required canvas and frame rate.

    ``expected_duration`` remains part of the call contract because the export
    handoff needs it, but product acceptance deliberately does not reject a
    readable video because its duration or H.264/H.265 encoding differs.
    """
    try:
        executable = Path(ffprobe_path) if ffprobe_path is not None else resolve_ffprobe()
    except ToolResolutionError as exc:
        raise V2ExportFailure("FFPROBE_MISSING", f"ffprobe 不可用：{exc}") from exc
    command = [str(executable), "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate", "-of", "json", str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, **no_window_kwargs())
        payload = json.loads(completed.stdout or "{}")
    except OSError as exc:
        raise V2ExportFailure("FFPROBE_MISSING", f"ffprobe 不可用：{exc}") from exc
    except ValueError as exc:
        raise V2ExportFailure("FFPROBE_FAILED", f"ffprobe 返回无效 JSON：{exc}") from exc
    if completed.returncode:
        raise V2ExportFailure("FFPROBE_FAILED", completed.stderr.strip()[-1000:] or "ffprobe 无法读取视频")
    video = next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), None)
    if not isinstance(video, dict):
        raise V2ExportFailure("VIDEO_STREAM_MISSING", "导出文件没有视频流")
    result = MediaInfo(str(path), path.stat().st_size, float(payload.get("format", {}).get("duration") or 0), int(video.get("width") or 0), int(video.get("height") or 0), _rate(video.get("avg_frame_rate") or video.get("r_frame_rate")), str(video.get("codec_name") or ""))
    if result.size_bytes <= 0 or result.width != width or result.height != height or abs(result.fps - fps) > .01:
        raise V2ExportFailure("MEDIA_CONTRACT_FAILED", f"媒体不符合合同：{result.width}x{result.height} {result.fps:.3f}fps {result.codec} {result.duration_seconds:.3f}s")
    return result


def wait_for_stable_new_file(path: Path, *, baseline: dict[str, Any], deadline: float, poll_seconds: float = 1.0, stable_samples: int = 2, now: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
    previous: tuple[int, int] | None = None
    stable = 0
    while now() < deadline:
        if source_is_new(path, baseline):
            current = file_baseline(path)
            signature = (int(current["size"]), int(current["mtime_ns"]))
            stable = stable + 1 if signature == previous else 1
            previous = signature
            if stable >= stable_samples:
                return
        else:
            previous, stable = None, 0
        sleep(poll_seconds)
    raise V2ExportFailure("OUTPUT_STABILITY_TIMEOUT", "原始 MP4 未在本次执行期限内出现并稳定")


def safe_move_verified_output(source: Path, target: Path) -> None:
    """Replace only after a fully copied temporary target exists; then remove source."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush(); os.fsync(output_stream.fileno())
        os.replace(temporary, target)
        source.unlink()
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise V2ExportFailure("OUTPUT_REPLACE_FAILED", f"已验收 MP4 无法安全替换正式文件：{exc}") from exc


def draft_duration_seconds(draft_path: Path) -> float:
    for name in ("draft_content.json", "draft_content.json.bak", "template.json.bak"):
        candidate = draft_path / name
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8-sig"))
            duration = float(payload.get("duration") or 0) / 1_000_000
            canvas = payload.get("canvas_config") or {}
            if duration > 0 and (int(canvas.get("width") or 0), int(canvas.get("height") or 0)) == (1080, 2400):
                return duration
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    raise V2ExportFailure("DRAFT_DURATION_UNREADABLE", f"无法读取 1080x2400 草稿时长：{draft_path}")
