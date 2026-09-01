"""Jianying 5.9 submit adapter with condition-based UI waits.

The upstream package still supplies the UIA controller and descriptors, but
this project owns the pre-submit sequence so it can wait for actual controls,
read live resolution/FPS values, and release foreground ownership immediately
after the final submit is accepted.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

from .executor import ExportFailure, ExportRequest, JianyingPage, PersistentSubmission


APP_NAME = "剪映专业版"
DESCRIPTION_PROPERTY = 30159
NAME_PROPERTY = 30005
VALUE_PROPERTY = 30045
PRE_SUBMIT_MAXIMUM_SECONDS = 180
UI_POLL_SECONDS = 0.15
WINDOW_REFRESH_SECONDS = 0.50
OPEN_DRAFT_TIMEOUT_SECONDS = 30.0
OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS = 30.0
PARAMETER_CONTROL_TIMEOUT_SECONDS = 10.0
EXPORT_DIALOG_RETRY_DELAY_SECONDS = 1.0
FINAL_EXPORT_DIALOG_MAX_RETRIES = 5
OCR_MINIMUM_CONFIDENCE = 0.90
_TRANSIENT_WINDOW_TRANSITION = "JIANYING_WINDOW_TRANSITIONING"

_RESOLUTION_VALUES = ("8K", "4K", "2K", "1080P", "720P", "480P")
_FRAMERATE_VALUES = ("24fps", "25fps", "30fps", "50fps", "60fps")
_OCR_ENGINE: Any | None = None


class _SubmissionAccepted(Exception):
    def __init__(self, source: Path) -> None: self.source = source


class ForegroundGuard(Protocol):
    """Bounded foreground ownership for one pre-submit UI sequence."""

    def acquire(self) -> None: ...
    def ensure(self) -> None: ...
    def release(self) -> None: ...


class _DefaultForegroundGuard:
    """Own input during pre-submit and bring Jianying forward once."""

    # Last-resort watchdog only. Normal progress is driven by control
    # conditions and per-stage deadlines below.
    _MAXIMUM_SECONDS = PRE_SUBMIT_MAXIMUM_SECONDS
    # Once the input lease is active, leave one short quiet interval before
    # changing foreground or issuing the first UIA operation. This prevents a
    # just-interrupted user gesture from racing the script's first action.
    _HANDOFF_GRACE_SECONDS = 1.0

    def __init__(self, *, sleep: Callable[[float], None] = time.sleep, maximize: bool = True) -> None:
        self._adapter: Any | None = None
        self._window: Any | None = None
        self._windows: dict[tuple[str, int], Any] = {}
        self._timeout_timer: threading.Timer | None = None
        self._lease_id = f"jianying59-submit-{uuid.uuid4()}"
        self._sleep = sleep
        self._maximize = maximize

    @staticmethod
    def _support() -> tuple[Any, Callable[..., Any]]:
        try:
            from server.windows_automation.jianying_adapter import (
                WindowsInputLeaseAdapter,
                foreground_jianying_window,
            )
        except Exception as exc:
            raise ExportFailure("FOREGROUND_GUARD_UNAVAILABLE", f"V2 前台接管组件不可用：{exc}") from exc
        return WindowsInputLeaseAdapter, foreground_jianying_window

    def acquire(self) -> None:
        if self._adapter is not None:
            return
        support = self._support()
        lease_type, foreground = support[0], support[1]
        self._adapter = lease_type()
        try:
            self._adapter.acquire(self._lease_id, maximum_seconds=self._MAXIMUM_SECONDS)
            self._sleep(self._HANDOFF_GRACE_SECONDS)
            try:
                self._window = foreground(maximize=self._maximize)
            except TypeError:
                # Compatibility with focused test doubles and older injected
                # foreground helpers that predate the maximize option.
                self._window = foreground()
            self._remember_window(self._window)
            self._timeout_timer = threading.Timer(self._MAXIMUM_SECONDS, self.release)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()
        except Exception as exc:
            self.release()
            raise ExportFailure("FOREGROUND_ACQUIRE_FAILED", f"剪映前台接管未建立：{exc}") from exc

    def ensure(self) -> None:
        if self._adapter is None or not self._adapter.is_active(self._lease_id):
            raise ExportFailure("FOREGROUND_LEASE_EXPIRED", "剪映前台接管已超时或被释放，停止后续自动化")
        # Do not re-activate or re-topmost during the UI flow. The input lease
        # protects the operation; repeated activation breaks Jianying's QML
        # dialog stacking.

    def release(self) -> None:
        timer, self._timeout_timer = self._timeout_timer, None
        if timer is not None:
            timer.cancel()
        try:
            if self._adapter is not None:
                self._adapter.release(self._lease_id)
        finally:
            self._adapter = None
            self._window = None
            self._windows.clear()

    @staticmethod
    def _window_key(window: Any) -> tuple[str, int]:
        try:
            return ("handle", int(window.handle))
        except Exception:
            return ("object", id(window))

    def _remember_window(self, window: Any) -> None:
        self._windows[self._window_key(window)] = window


class _ControlProxy:
    """Delegates every upstream control operation except final-submit tracing."""

    def __init__(self, raw: Any, owner: "PassiveUpstreamController") -> None:
        self._raw, self._owner = raw, owner

    def __getattr__(self, name: str) -> Any: return getattr(self._raw, name)

    def Control(self, *args: Any, **kwargs: Any) -> "_ControlProxy": return _ControlProxy(self._raw.Control(*args, **kwargs), self._owner)
    def TextControl(self, *args: Any, **kwargs: Any) -> "_ControlProxy": return _ControlProxy(self._raw.TextControl(*args, **kwargs), self._owner)
    def GroupControl(self, *args: Any, **kwargs: Any) -> "_ControlProxy": return _ControlProxy(self._raw.GroupControl(*args, **kwargs), self._owner)
    def GetParentControl(self, *args: Any, **kwargs: Any) -> "_ControlProxy | None":
        parent = self._raw.GetParentControl(*args, **kwargs)
        return _ControlProxy(parent, self._owner) if parent is not None else None
    def GetSiblingControl(self, *args: Any, **kwargs: Any) -> "_ControlProxy | None":
        sibling = self._raw.GetSiblingControl(*args, **kwargs)
        return _ControlProxy(sibling, self._owner) if sibling is not None else None

    def GetPropertyValue(self, property_id: int) -> Any:
        value = self._raw.GetPropertyValue(property_id)
        if property_id == DESCRIPTION_PROPERTY and isinstance(value, str) and value.casefold().endswith(".mp4"):
            self._owner.source_output_path = Path(value)
        return value

    def Click(self, *args: Any, **kwargs: Any) -> Any:
        is_final = _description(self._raw) == "ExportOkBtn"
        try:
            result = self._raw.Click(*args, **kwargs)
        except Exception:
            if is_final:
                self._owner._operation("CLICK_EXPORT_OK", "点击最终「导出」", "ACTION", "ExportOkBtn（最终导出按钮）", "FAILED", current_result="点击失败")
            raise
        if is_final:
            self._owner._operation("CLICK_EXPORT_OK", "点击最终「导出」", "ACTION", "ExportOkBtn（最终导出按钮）", "DONE", current_result="点击已返回")
            # Final submission ends active desktop automation.  Rendering and
            # file verification are passive, so do not keep the user desktop
            # locked while waiting for Jianying.
            self._owner.release_pre_submit()
            self._owner.final_submit_clicked()
        return result


class PassiveUpstreamController:
    """Compatibility subclass factory kept separate to avoid copying upstream code."""

    def __init__(self, controller_type: type, *, uia: Any | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic,
                 foreground_guard: ForegroundGuard | None = None,
                 trace_sink: Callable[[dict[str, Any]], None] | None = None,
                 debug_sink: Callable[[dict[str, Any]], None] | None = None,
                 operation_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        # A dynamic subclass lets inherited export_draft run unchanged while
        # get_window wraps returned controls. No Skill source is imported.
        owner = self

        self._uia, self._sleep, self._monotonic, self._raw_app = uia, sleep, monotonic, None
        self._trace_sink, self._trace_started_at = trace_sink, monotonic()
        self._debug_sink = debug_sink
        self._operation_sink = operation_sink
        self._operation_started_at: dict[str, tuple[float, float]] = {}
        self.source_output_path: Path | None = None
        self._home_window: Any | None = None
        self._upstream_windows: list[Any] = []
        self._foreground_guard = foreground_guard or _DefaultForegroundGuard()
        self._pre_submit_released = False

        class _Controller(controller_type):
            def get_window(self) -> None:
                if owner._uia is None:
                    super().get_window()
                else:
                    owner._bind_window_passively(
                        self,
                        inspect_export_container=not bool(getattr(self, "_v1_waiting_for_editor", False)),
                    )
                owner._remember_upstream_window(self.app)
                owner._raw_app = self.app
                self.app = _ControlProxy(self.app, owner)

        self._controller_type = _Controller

    def _operation(self, operation_id: str, operation_name_zh: str, operation_type: str,
                   target: str, status: str, *, poll_count: int | None = None,
                   current_result: str = "") -> None:
        if self._operation_sink is None:
            return
        now_wall, now_mono = time.time(), self._monotonic()
        if status == "STARTED" or operation_id not in self._operation_started_at:
            self._operation_started_at[operation_id] = (now_wall, now_mono)
        started_wall, started_mono = self._operation_started_at[operation_id]
        payload = {
            "operation_id": operation_id,
            "operation_name_zh": operation_name_zh,
            "operation_type": operation_type,
            "target": target,
            "status": status,
            "started_at": started_wall,
            "elapsed_ms": round(max(0.0, now_mono - started_mono) * 1000.0, 1),
            "current_result": current_result,
        }
        if poll_count is not None:
            payload["poll_count"] = poll_count
        try:
            self._operation_sink(payload)
        except Exception:
            # Operation diagnostics are cosmetic and must never affect UIA.
            pass
        if status in {"DONE", "FOUND", "FAILED"}:
            self._operation_started_at.pop(operation_id, None)

    def _operation_start(self, operation_id: str, name: str, kind: str, target: str) -> None:
        self._operation(operation_id, name, kind, target, "STARTED")

    def _bind_window_passively(self, controller: Any, *, inspect_export_container: bool = True) -> None:
        """Bind the current 5.9 UIA surface without changing focus or z-order."""
        timing: dict[str, float] = {}
        self._last_window_bind_timing = timing

        def timed(name: str, action: Callable[[], Any]) -> Any:
            started = time.perf_counter()
            try:
                return action()
            finally:
                timing[name] = round((time.perf_counter() - started) * 1000.0, 1)

        # Query the two known top-level surfaces directly.  Walking the root
        # UIA tree during the HomeWindow -> MainWindow transition can block for
        # about ten seconds even after the editor and its export button exist.
        # Keep the walk only as a compatibility fallback for focused fakes.
        editors: list[Any] = []
        homes: list[Any] = []
        window_factory = getattr(self._uia, "WindowControl", None)
        if callable(window_factory):
            try:
                editor = timed("创建MainWindow查询", lambda: window_factory(
                    searchDepth=1, searchInterval=0, Name=APP_NAME, AutomationId="MainWindow"
                ))
                editors = [editor] if editor is not None and bool(timed("检查MainWindow", lambda: editor.Exists(0))) else []
                # While a draft is opening we only need MainWindow.  Asking
                # UIA for the old HomeWindow as it is being destroyed can
                # block for roughly ten seconds even after MainWindow exists.
                if inspect_export_container:
                    home = timed("创建HomeWindow查询", lambda: window_factory(
                        searchDepth=1, searchInterval=0, Name=APP_NAME, AutomationId="HomeWindow"
                    ))
                    homes = [home] if home is not None and bool(timed("检查HomeWindow", lambda: home.Exists(0))) else []
            except Exception:
                editors, homes = [], []
        if not editors and not homes and not inspect_export_container:
            # During HomeWindow -> MainWindow recreation, direct UIA lookup
            # can briefly return no MainWindow.  This is a normal transient
            # condition.  Do not fall back to a root-tree walk here: that walk
            # can block for ten seconds after the editor is already visible.
            raise ExportFailure(_TRANSIENT_WINDOW_TRANSITION, "剪映正在切换首页与剪辑页")
        if not editors and not homes:
            root = timed("获取UIARoot", self._uia.GetRootControl)
            candidates = [
                control for control, depth in timed("遍历UIARoot", lambda: list(self._uia.WalkControl(root, maxDepth=2)))
                if depth > 0 and str(getattr(control, "Name", "")) == APP_NAME
                and str(getattr(control, "AutomationId", "")) in {"HomeWindow", "MainWindow"}
            ]
            editors = [item for item in candidates if str(getattr(item, "AutomationId", "")) == "MainWindow"]
            homes = [item for item in candidates if str(getattr(item, "AutomationId", "")) == "HomeWindow"]
        if len(editors) == 1:
            main, status = editors[0], "edit"
        elif not editors and len(homes) == 1:
            main, status = homes[0], "home"
        elif not editors and not homes:
            # Jianying briefly recreates its top-level QML surface while a
            # draft opens. This is a page transition, not an ambiguous window;
            # callers with a bounded control wait should retry passively.
            raise ExportFailure(_TRANSIENT_WINDOW_TRANSITION, "剪映正在切换首页与剪辑页")
        else:
            raise ExportFailure("JIANYING_WINDOW_AMBIGUOUS", f"无法唯一绑定剪映页面：编辑页 {len(editors)}，首页 {len(homes)}")
        # Jianying 5.9 exposes the parameter surface as an Export_QMLTYPE
        # container, not a WindowControl titled "导出".  Looking for the
        # wrong control type is what kept the old binding on MainWindow until
        # a slow fallback pass happened.
        export: Any | None = None
        generic_control = getattr(main, "Control", None)
        supports_generic_control = callable(generic_control)
        if inspect_export_container and supports_generic_control:
            try:
                candidate = generic_control(
                    searchDepth=1, searchInterval=0, AutomationId="ExportWindow_Container",
                )
                if candidate is not None and bool(candidate.Exists(0)):
                    export = candidate
            except Exception:
                export = None
        # In Jianying 5.9 the editor's visible top-right "导出" caption is
        # not a parameter window.  A title-based WindowControl fallback can
        # therefore traverse the editor for seconds and bind the wrong
        # surface.  Use it only for focused compatibility fakes that do not
        # support the native ExportWindow_Container locator at all.
        if inspect_export_container and export is None and not supports_generic_control:
            export = main.WindowControl(searchDepth=1, searchInterval=0, Name="导出")
        if status == "home":
            self._home_window = main
        if export is not None and export.Exists(0):
            controller.app, controller.app_status = export, "pre_export"
        else:
            controller.app, controller.app_status = main, status

    def ensure_foreground(self) -> None:
        self._foreground_guard.ensure()

    def export_until_submission(self, request: ExportRequest) -> Path:
        try:
            from pyJianYingDraft import ExportFramerate, ExportResolution
            from pyJianYingDraft.jianying_controller import ControlFinder
            self._foreground_guard.acquire()
            controller = self._controller_type()
            export_button = self._open_draft_until_editor(controller, request.draft_name, ControlFinder)
            export_dialog = self._open_export_dialog(
                controller, ControlFinder, export_button=export_button,
                wait_for_ready=request.apply_export_parameters,
            )
            if not request.apply_export_parameters and export_dialog is not None:
                controller.app = export_dialog
            if request.apply_export_parameters:
                self._ensure_export_parameter(
                    controller, ControlFinder, input_descriptor="ExportSharpnessInput",
                    expected=ExportResolution.RES_1080P.value, setting_label="分辨率",
                    allow_ocr=request.allow_parameter_ocr,
                    force_select=request.force_parameter_selection,
                )
                self._ensure_export_parameter(
                    controller, ControlFinder, input_descriptor="FrameRateInput",
                    expected=ExportFramerate.FR_30.value, setting_label="视频帧率",
                    allow_ocr=request.allow_parameter_ocr,
                    force_select=request.force_parameter_selection,
                )
            else:
                self._operation_start("SKIP_PARAMETERS", "任务跳过参数修改", "ACTION", "导出参数")
                self._operation("SKIP_PARAMETERS", "任务跳过参数修改", "ACTION", "导出参数", "DONE", current_result="按导出规则跳过")
            path_anchor = self._wait_for_control(
                controller, "导出参数路径",
                lambda app: app.TextControl(searchDepth=2, Compare=ControlFinder.desc_matcher("ExportPath")),
                timeout_seconds=PARAMETER_CONTROL_TIMEOUT_SECONDS,
                # The finished-video branch has already bound the actual
                # ExportWindow_Container below.  Rebinding the top-level
                # window here can put the path search back on the editor
                # root while Jianying is still transitioning.
                refresh_window=False,
                debug_stage="WAIT_EXPORT_PATH",
                debug_controls=lambda found: {"ExportPath": found},
                operation_id="FIND_EXPORT_PATH", operation_name_zh="查找导出路径", operation_target="ExportPath（剪映输出路径控件）",
            )
            self._operation_start("READ_EXPORT_PATH", "读取剪映输出路径", "ACTION", "MP4 输出路径")
            self._capture_native_output_path(path_anchor)
            self._operation("READ_EXPORT_PATH", "读取剪映输出路径", "ACTION", "MP4 输出路径", "DONE", current_result="路径已读取")
            final_button = self._wait_for_control(
                controller, "最终导出按钮",
                lambda app: app.TextControl(searchDepth=2, Compare=ControlFinder.desc_matcher("ExportOkBtn", exact=True)),
                timeout_seconds=PARAMETER_CONTROL_TIMEOUT_SECONDS,
                refresh_window=False,
                debug_stage="WAIT_EXPORT_OK",
                debug_controls=lambda found: {"ExportOkBtn": found},
                operation_id="FIND_EXPORT_OK", operation_name_zh="查找最终「导出」按钮", operation_target="ExportOkBtn（最终导出按钮）",
            )
            self._trace("最终导出按钮可见", stage="WAIT_EXPORT_OK", result="OK")
            self._operation_start("CLICK_EXPORT_OK", "点击最终「导出」", "ACTION", "ExportOkBtn（最终导出按钮）")
            self._trace("点击最终导出", stage="SUBMIT_EXPORT")
            final_button.Click(simulateMove=False)
        except _SubmissionAccepted as accepted:
            return accepted.source
        except ExportFailure:
            raise
        except Exception as exc:
            raise ExportFailure("UPSTREAM_EXPORT_FAILED", f"上游 JianyingController 导出前台流程失败：{exc}") from exc
        finally:
            # This runs both after accepted final submission and every failure.
            # Rendering/file verification never owns the user desktop.
            self.release_pre_submit()
        raise ExportFailure("UPSTREAM_POST_SUBMIT_ESCAPE_FAILED", "上游流程未经被动提交边界即返回，拒绝视为成功")

    def release_pre_submit(self) -> None:
        """Release input and all tracked Jianying windows exactly once."""
        if self._pre_submit_released:
            return
        self._pre_submit_released = True
        self._release_upstream_topmost()
        self._foreground_guard.release()

    def _open_draft_until_editor(self, controller: Any, draft_name: str, finder: Any) -> Any:
        """Shared exact-draft navigation ending only after editor readiness."""
        return self._open_draft(controller, draft_name, finder)

    def _open_draft(self, controller: Any, draft_name: str, finder: Any) -> Any:
        if getattr(controller, "app_status", None) not in {None, "home"}:
            raise ExportFailure("HOME_STATE_UNCONFIRMED", "提交前未确认剪映首页，拒绝使用固定等待切换")
        self._trace("定位草稿开始", draft_name, stage="LOCATE_DRAFT", waiting_for="首页完整草稿名称")
        # The homepage may still be filtered to the preceding task.  Always
        # replace that filter with this task's full draft name before looking
        # at any card, so an off-screen or hidden draft can never be clicked.
        title, button = self._search_draft(controller, draft_name, finder)
        self._operation_start("CHECK_DRAFT_BOUNDS", "检查草稿点击区域", "ACTION", "草稿标题与父控件区域")
        if not self._draft_click_is_safe(title, button):
            self._operation("CHECK_DRAFT_BOUNDS", "检查草稿点击区域", "ACTION", "搜索结果草稿区域", "FAILED", current_result="搜索结果仍不可安全点击")
            raise ExportFailure("DRAFT_NOT_SAFE_TO_CLICK", "草稿不在剪映首页安全点击区域")
        self._operation("CHECK_DRAFT_BOUNDS", "检查草稿点击区域", "ACTION", "搜索结果草稿区域", "DONE", current_result="搜索结果点击区域安全")
        self._trace("首页草稿可见", draft_name, stage="LOCATE_DRAFT", result="OK")
        self._operation_start("CLICK_DRAFT", "点击目标草稿", "ACTION", "目标草稿卡片")
        self._trace("点击首页草稿", draft_name, stage="OPEN_DRAFT", waiting_for="首页草稿卡片")
        try:
            button.Click(simulateMove=False)
        except Exception:
            self._operation("CLICK_DRAFT", "点击目标草稿", "ACTION", "目标草稿卡片", "FAILED", current_result="点击失败")
            raise
        self._operation("CLICK_DRAFT", "点击目标草稿", "ACTION", "目标草稿卡片", "DONE", current_result="点击已返回")
        self._operation_start("WAIT_MAIN_WINDOW", "等待剪辑窗口出现", "WAIT", "MainWindow（剪辑窗口）")
        self._operation_start("FIND_EDITOR_EXPORT_BUTTON", "查找右上角「导出」按钮", "WAIT", "MainWindowTitleBarExportBtn（剪辑页导出按钮）")
        controller._v1_waiting_for_editor = True
        try:
            export_button = self._wait_for_control(
                controller, "编辑页导出按钮",
                lambda app: self._find_editor_export_button(app, finder),
                timeout_seconds=OPEN_DRAFT_TIMEOUT_SECONDS,
                debug_stage="WAIT_EDITOR_EXPORT_BUTTON",
                debug_controls=lambda found: {
                    "HomeWindow": getattr(controller, "app_status", "") == "home",
                    "MainWindow": getattr(controller, "app_status", "") == "edit",
                    "MainWindowTitleBarExportBtn": found,
                },
            )
        finally:
            controller.__dict__.pop("_v1_waiting_for_editor", None)
        self._trace("编辑页导出按钮可见", stage="WAIT_EDITOR_EXPORT_BUTTON", result="OK")
        return export_button

    def _search_draft(self, controller: Any, draft_name: str, finder: Any) -> tuple[Any, Any]:
        """Use UIA ValuePattern to reveal an off-screen draft before clicking."""
        self._operation_start("SEARCH_DRAFT", "搜索离屏草稿", "ACTION", "首页搜索框")
        self._trace("搜索草稿开始", draft_name, stage="SEARCH_DRAFT", waiting_for="首页搜索输入框")
        search = self._wait_for_control(
            controller, "首页搜索输入框", self._find_search_input,
            timeout_seconds=OPEN_DRAFT_TIMEOUT_SECONDS,
            operation_id="FIND_SEARCH_BOX", operation_name_zh="查找首页搜索框", operation_target="首页搜索输入框",
        )
        try:
            pattern = search.GetValuePattern()
            pattern.SetValue(draft_name)
            self._operation("SEARCH_DRAFT", "搜索离屏草稿", "ACTION", "首页搜索框", "DONE", current_result="完整草稿名已写入")
        except Exception as exc:
            self._operation("SEARCH_DRAFT", "搜索离屏草稿", "ACTION", "首页搜索框", "FAILED", current_result="无法写入搜索框")
            raise ExportFailure("DRAFT_SEARCH_INPUT_FAILED", f"无法写入首页搜索框：{exc}") from exc
        title = self._wait_for_control(
            controller, "搜索后的唯一完整草稿名称",
            lambda app: app.TextControl(searchDepth=2, Compare=finder.desc_matcher(f"HomePageDraftTitle:{draft_name}", exact=True)),
            timeout_seconds=OPEN_DRAFT_TIMEOUT_SECONDS,
            operation_id="REFIND_DRAFT", operation_name_zh="重新获取搜索结果草稿",
            operation_target=f"HomePageDraftTitle:{draft_name}",
        )
        self._operation_start("GET_DRAFT_PARENT", "获取目标草稿父控件", "ACTION", "搜索结果草稿标题")
        button = title.GetParentControl()
        if button is None:
            self._operation("GET_DRAFT_PARENT", "获取目标草稿父控件", "ACTION", "搜索结果草稿标题", "FAILED", current_result="未找到父控件")
            raise ExportFailure("DRAFT_BUTTON_MISSING", "搜索结果草稿标题没有可点击父控件")
        self._operation("GET_DRAFT_PARENT", "获取目标草稿父控件", "ACTION", "搜索结果草稿标题", "DONE", current_result="已找到父控件")
        self._trace("搜索草稿完成", draft_name, stage="SEARCH_DRAFT", result="OK")
        return title, button

    @staticmethod
    def _find_search_input(app: Any) -> Any:
        def match(control: Any, _depth: int) -> bool:
            values = [getattr(control, key, "") for key in ("Name", "AutomationId", "ClassName")]
            values.append(_description(control))
            text = " ".join(str(value or "") for value in values).casefold()
            if "search" in text or "搜索" in text:
                return True
            # Jianying 5.9's homepage search field is an EditControl whose
            # QML accessibility properties are empty while it is collapsed.
            # It remains directly writable through ValuePattern, so recognize
            # its stable QML control family without clicking an off-screen
            # draft or relying on screen coordinates.
            return str(getattr(control, "ClassName", "") or "").startswith("TextField_QMLTYPE")
        return app.EditControl(searchDepth=2, Compare=match)

    def _draft_click_is_safe(self, title: Any, parent: Any) -> bool:
        home = self._home_window
        if home is None:
            # In-process upstream fakes do not expose a top-level UIA window;
            # real Windows runs bind HomeWindow before this method is reached.
            return self._uia is None
        home_rect = _control_rect(home)
        title_rect, parent_rect = _control_rect(title), _control_rect(parent)
        if home_rect is None or title_rect is None or parent_rect is None:
            return False
        if _control_offscreen(title) or _control_offscreen(parent):
            return False
        if not _rect_contains(home_rect, title_rect) or not _rect_contains(home_rect, parent_rect):
            return False
        center = _rect_center(parent_rect)
        return center is not None and _rect_contains(home_rect, (center[0], center[1], center[0], center[1]))

    def _open_export_dialog(
        self, controller: Any, finder: Any, *, export_button: Any | None = None,
        wait_for_ready: bool = True,
    ) -> Any:
        if export_button is None:
            export_button = self._wait_for_control(
                controller, "编辑页导出按钮",
                lambda app: self._find_editor_export_button(app, finder),
                timeout_seconds=OPEN_DRAFT_TIMEOUT_SECONDS,
            )
        self._operation_start("CLICK_EDITOR_EXPORT", "点击右上角「导出」", "ACTION", "MainWindowTitleBarExportBtn（剪辑页导出按钮）")
        self._trace("点击打开导出窗口", stage="OPEN_EXPORT_DIALOG")
        try:
            export_button.Click(simulateMove=False)
        except Exception:
            self._operation("CLICK_EDITOR_EXPORT", "点击右上角「导出」", "ACTION", "MainWindowTitleBarExportBtn（剪辑页导出按钮）", "FAILED", current_result="点击失败")
            raise
        self._operation("CLICK_EDITOR_EXPORT", "点击右上角「导出」", "ACTION", "MainWindowTitleBarExportBtn（剪辑页导出按钮）", "DONE", current_result="点击已返回")
        if not wait_for_ready:
            # Finished videos have no parameter work.  Bind the real 5.9
            # export container from the already-confirmed MainWindow, then
            # let the existing ExportPath wait determine readiness.
            # Real UIA controls expose Control().  Tiny legacy test doubles
            # expose their child controls directly, so they are already the
            # correct root and need no artificial container wait.
            if not callable(getattr(controller.app, "Control", None)):
                return controller.app
            return self._wait_for_finished_export_dialog(controller, finder, export_button)
        try:
            parameter_control = self._wait_for_export_dialog(controller, finder, export_button)
        except Exception as exc:
            self._operation("WAIT_EXPORT_WINDOW", "等待导出设置窗口", "WAIT", "ExportWindow（导出设置窗口）", "FAILED", current_result=f"等待失败：{type(exc).__name__}")
            raise
        self._trace("导出参数窗口已被识别", stage="WAIT_EXPORT_SETTINGS", result="OK")
        self._trace("导出参数控件可操作", stage="WAIT_EXPORT_SETTINGS", result="OK")
        return parameter_control

    def _wait_for_finished_export_dialog(self, controller: Any, finder: Any, export_button: Any) -> Any:
        """Retry the editor export button only while Final remains on the editor page."""
        deadline = self._monotonic() + OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS
        last_retry_at = self._monotonic()
        retry_count = 0
        while True:
            try:
                if getattr(controller, "app_status", "") == "pre_export":
                    if bool(controller.app.Exists(0)):
                        return controller.app
                else:
                    container = self._find_export_container(controller.app)
                    if container is not None and bool(container.Exists(0)):
                        return container
            except ExportFailure as exc:
                if exc.code != _TRANSIENT_WINDOW_TRANSITION:
                    raise
            except Exception:
                # Jianying can reject UIA queries while its QML export panel is loading.
                pass

            now = self._monotonic()
            if (
                getattr(controller, "app_status", "") == "edit"
                and retry_count < FINAL_EXPORT_DIALOG_MAX_RETRIES
                and now - last_retry_at >= EXPORT_DIALOG_RETRY_DELAY_SECONDS
            ):
                # Keep the fast existing MainWindow probe on the normal path.
                # Rebind only when a retry is actually needed, and avoid the
                # expensive HomeWindow query while Jianying is transitioning.
                if self._uia is None:
                    controller.get_window()
                else:
                    self._bind_window_passively(controller, inspect_export_container=False)
                    self._remember_upstream_window(controller.app)
                    self._raw_app = controller.app
                    controller.app = _ControlProxy(controller.app, self)
                container = self._find_export_container(controller.app)
                if container is not None and bool(container.Exists(0)):
                    return container
                fresh_button = self._find_editor_export_button(controller.app, finder)
                if fresh_button is not None and bool(fresh_button.Exists(0)):
                    retry_count += 1
                    self._trace(
                        "成片导出参数页未出现，重新定位后重试点击导出按钮",
                        f"第 {retry_count}/{FINAL_EXPORT_DIALOG_MAX_RETRIES} 次",
                        stage="WAIT_EXPORT_SETTINGS", waiting_for="ExportWindow_Container",
                    )
                    fresh_button.Click(simulateMove=False)
                last_retry_at = now
            if now >= deadline:
                raise ExportFailure("UI_CONDITION_TIMEOUT", f"等待导出参数页超过 {OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS:.0f} 秒")
            self._sleep(UI_POLL_SECONDS)

    @staticmethod
    def _find_export_container(app: Any) -> Any:
        factory = getattr(app, "Control", None)
        if not callable(factory):
            # Compatibility test doubles already expose the parameter controls
            # from their current application root.
            return app
        return factory(
            searchDepth=1, searchInterval=0, AutomationId="ExportWindow_Container",
        )

    @staticmethod
    def _find_editor_export_button(app: Any, finder: Any) -> Any:
        """Find the 5.9 title-bar button by its parent, then verify its child label."""
        group_factory = getattr(app, "GroupControl", None)
        if callable(group_factory):
            try:
                candidate = group_factory(
                    searchDepth=1, searchInterval=0,
                    Compare=lambda control, depth: depth == 1
                    and str(getattr(control, "ClassName", "")).startswith("VEShellButton_QMLTYPE_"),
                )
                if candidate is not None and bool(candidate.Exists(0)):
                    label = candidate.TextControl(
                        searchDepth=1, searchInterval=0,
                        Compare=finder.desc_matcher("MainWindowTitleBarExportBtn", depth=1, exact=True),
                    )
                    if label is not None and bool(label.Exists(0)):
                        return candidate
            except Exception:
                pass
        return app.TextControl(
            searchDepth=2, searchInterval=0,
            Compare=finder.desc_matcher("MainWindowTitleBarExportBtn"),
        )

    def _wait_for_export_dialog(self, controller: Any, finder: Any, export_button: Any) -> Any:
        """Wait for the slow 5.9 dialog and retry the editor button once per second.

        The editor can expose its export button before preview rendering is
        complete. Jianying ignores clicks during that interval, so a bounded
        one-second retry cadence is used until the resolution selector is
        available.  The final-export control is intentionally not the entry
        condition: Jianying can draw the parameter panel and expose the
        selector before UIA reports that footer button. The output path and
        final button are still read separately before final submission.
        This is the template-only readiness wait. Finished videos proceed
        directly to their existing ExportPath wait after the editor click.
        """
        deadline = self._monotonic() + OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS
        last_refresh_at: float | None = None
        last_retry_at = self._monotonic()
        stable = 0
        control: Any | None = None
        poll_count = 0
        self._operation_start("WAIT_EXPORT_WINDOW", "等待导出设置窗口", "WAIT", "ExportWindow（导出设置窗口）")
        while True:
            poll_count += 1
            now = self._monotonic()
            try:
                if last_refresh_at is None or now - last_refresh_at >= WINDOW_REFRESH_SECONDS:
                    controller.get_window()
                    last_refresh_at = now
                if getattr(controller, "app_status", "") == "pre_export" and "FIND_SETTINGS_GROUP" not in self._operation_started_at:
                    self._operation_start("FIND_SETTINGS_GROUP", "查找参数区域", "WAIT", "Settings Group（参数区域）")
                group = controller.app.GroupControl(
                    searchDepth=1, Compare=finder.class_name_matcher("PanelSettingsGroup_QMLTYPE")
                )
                if getattr(controller, "app_status", "") == "pre_export" and "FIND_RESOLUTION_CONTROL" not in self._operation_started_at:
                    self._operation_start("FIND_RESOLUTION_CONTROL", "查找分辨率设置", "WAIT", "ExportSharpnessInput（分辨率控件）")
                control = group.TextControl(
                    searchDepth=2, Compare=finder.desc_matcher("ExportSharpnessInput")
                )
                if control is not None and bool(control.Exists(0)):
                    stable += 1
                    self._debug_wait(
                        "WAIT_EXPORT_SETTINGS", "ExportSharpnessInput", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS,
                        poll_count=poll_count, controls={
                            "Export Window": getattr(controller, "app_status", "") == "pre_export",
                            "Settings Group": bool(group.Exists(0)),
                            "ExportSharpnessInput": True,
                        },
                    )
                    if stable >= 2:
                        return control
                else:
                    stable = 0
                    self._debug_wait(
                        "WAIT_EXPORT_SETTINGS", "ExportSharpnessInput", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS,
                        poll_count=poll_count, controls={
                            "Export Window": getattr(controller, "app_status", "") == "pre_export",
                            "Settings Group": bool(group.Exists(0)),
                            "ExportSharpnessInput": False,
                        },
                    )
            except ExportFailure as exc:
                if exc.code == _TRANSIENT_WINDOW_TRANSITION:
                    stable = 0
                else:
                    raise
            except Exception:
                stable = 0
                self._debug_wait(
                    "WAIT_EXPORT_SETTINGS", "ExportSharpnessInput", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS,
                    poll_count=poll_count, controls={
                        "Export Window": getattr(controller, "app_status", "") == "pre_export",
                        "Settings Group": False,
                        "ExportSharpnessInput": False,
                    },
                )

            now = self._monotonic()
            if now - last_retry_at >= EXPORT_DIALOG_RETRY_DELAY_SECONDS:
                self._trace("导出参数页未出现，重试点击导出按钮", stage="WAIT_EXPORT_SETTINGS", waiting_for="ExportSharpnessInput")
                export_button.Click(simulateMove=False)
                last_retry_at = now
            if now >= deadline:
                raise ExportFailure("UI_CONDITION_TIMEOUT", f"等待导出参数页超过 {OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS:.0f} 秒")
            self._sleep(UI_POLL_SECONDS)

    def _capture_native_output_path(self, path_anchor: Any) -> None:
        sibling = path_anchor.GetSiblingControl(lambda _control: True)
        if sibling is None:
            raise ExportFailure("UPSTREAM_SOURCE_PATH_UNREADABLE", "导出参数窗缺少 MP4 路径控件")
        value = str(sibling.GetPropertyValue(DESCRIPTION_PROPERTY) or "").strip()
        if value.casefold().endswith(".mp4"):
            self.source_output_path = Path(value)
        if self.source_output_path is None or not self.source_output_path.is_absolute():
            raise ExportFailure("UPSTREAM_SOURCE_PATH_UNREADABLE", "导出参数窗未回读唯一绝对 MP4 源路径")
        self._trace("导出路径读取完成", str(self.source_output_path), stage="WAIT_EXPORT_PATH", result="OK")

    def _ensure_export_parameter(
        self, controller: Any, finder: Any, *, input_descriptor: str, expected: str,
        setting_label: str, allow_ocr: bool = True, force_select: bool = False,
    ) -> None:
        control = self._wait_for_control(
            controller, setting_label,
            lambda app: app.GroupControl(searchDepth=1, Compare=finder.class_name_matcher("PanelSettingsGroup_QMLTYPE")).TextControl(
                searchDepth=2, Compare=finder.desc_matcher(input_descriptor)
            ),
            timeout_seconds=PARAMETER_CONTROL_TIMEOUT_SECONDS,
            refresh_window=False,
            operation_id="FIND_RESOLUTION_CONTROL" if input_descriptor == "ExportSharpnessInput" else "FIND_FRAME_RATE_CONTROL",
            operation_name_zh="查找分辨率设置" if input_descriptor == "ExportSharpnessInput" else "查找帧率设置",
            operation_target=f"{input_descriptor}（{setting_label}控件）",
        )
        if force_select:
            self._trace(f"{setting_label}固定选择", expected, stage="APPLY_EXPORT_PARAMETERS", waiting_for=setting_label)
            current = None
        else:
            current = self._read_current_parameter(control, expected, allow_ocr=allow_ocr)
        if current is None and not force_select:
            raise ExportFailure("PARAMETER_VALUE_UNREADABLE", f"无法读取当前{setting_label}，已停止避免重复猜点")
        if not force_select:
            if current == expected.casefold():
                self._trace(f"{setting_label}读取完成", f"当前值={current}", stage="APPLY_EXPORT_PARAMETERS", result="OK")
                self._operation(
                    "SET_RESOLUTION" if setting_label == "分辨率" else "SET_FRAME_RATE",
                    f"设置{expected}", "ACTION", f"{setting_label}控件", "DONE", current_result="原值已符合要求",
                )
                return
            self._trace(f"{setting_label}读取完成", f"当前值={current}，需要修改", stage="APPLY_EXPORT_PARAMETERS")
        operation_id = "SET_RESOLUTION" if setting_label == "分辨率" else "SET_FRAME_RATE"
        self._operation_start(operation_id, f"设置{expected}", "ACTION", f"{setting_label}控件")
        self._trace(f"点击{setting_label}下拉框", expected)
        try:
            control.Click(simulateMove=False)
        except Exception:
            self._operation(operation_id, f"设置{expected}", "ACTION", f"{setting_label}控件", "FAILED", current_result="控件点击失败")
            raise
        self._trace(f"{setting_label}下拉框已点击", expected)
        # Reuse the maintained Jianying Editor export pattern: 5.9 commonly
        # exposes the menu label as "1080", while the closed field says
        # "1080P". Prefer Name and retain the descriptor fallback.
        self._sleep(0.5)
        option_name = "1080" if expected.casefold() == "1080p" else expected
        option = controller.app.TextControl(searchDepth=5, Name=option_name)
        if not option.Exists(0.5):
            option = controller.app.TextControl(searchDepth=5, Compare=finder.desc_matcher(option_name))
        if not option.Exists(0.5):
            raise ExportFailure("PARAMETER_OPTION_UNAVAILABLE", f"导出窗口未提供{setting_label}选项 {expected}")
        self._trace(f"{setting_label}菜单项已找到", expected)
        try:
            option.Click(simulateMove=False)
        except Exception:
            self._operation(operation_id, f"设置{expected}", "ACTION", f"{setting_label}控件", "FAILED", current_result="菜单项点击失败")
            raise
        if force_select:
            self._trace(f"{setting_label}选择完成", expected)
            self._operation(operation_id, f"设置{expected}", "ACTION", f"{setting_label}控件", "DONE", current_result="已选择目标值")
            return
        self._wait_until(
            f"{setting_label}已更新为 {expected}",
            lambda: self._parameter_value_matches(controller, finder, input_descriptor, expected, allow_ocr),
            timeout_seconds=PARAMETER_CONTROL_TIMEOUT_SECONDS,
        )
        self._trace(f"{setting_label}修改完成", expected)
        self._operation(operation_id, f"设置{expected}", "ACTION", f"{setting_label}控件", "DONE", current_result="目标值已确认")

    def _parameter_value_matches(
        self, controller: Any, finder: Any, input_descriptor: str, expected: str, allow_ocr: bool = True,
    ) -> bool:
        self.ensure_foreground()
        controller.get_window()
        group = controller.app.GroupControl(searchDepth=1, Compare=finder.class_name_matcher("PanelSettingsGroup_QMLTYPE"))
        if not group.Exists(0):
            return False
        control = group.TextControl(searchDepth=2, Compare=finder.desc_matcher(input_descriptor))
        return bool(control.Exists(0) and self._read_current_parameter(control, expected, allow_ocr=allow_ocr) == expected.casefold())

    def _wait_for_control(
        self, controller: Any, label: str, create: Callable[[Any], Any], *, timeout_seconds: float,
        refresh_window: bool = True, stable_samples: int = 1, debug_stage: str = "",
        debug_controls: Callable[[bool], dict[str, bool]] | None = None,
        operation_id: str = "", operation_name_zh: str = "", operation_target: str = "",
    ) -> Any:
        control: Any | None = None
        last_refresh_at: float | None = None
        stable = 0
        poll_count = 0
        if operation_id:
            self._operation_start(operation_id, operation_name_zh or label, "WAIT", operation_target or label)

        def available() -> bool:
            nonlocal control, last_refresh_at, stable, poll_count
            poll_count += 1
            refresh_ms = create_ms = exists_ms = 0.0
            try:
                now = self._monotonic()
                # A refresh may activate the upstream window. It is necessary
                # after a page transition, but repeatedly doing it while a
                # QML dialog is animating makes that dialog flicker.
                if refresh_window and (last_refresh_at is None or now - last_refresh_at >= WINDOW_REFRESH_SECONDS):
                    started = self._monotonic()
                    controller.get_window()
                    refresh_ms = max(0.0, self._monotonic() - started) * 1000.0
                    last_refresh_at = now
                started = self._monotonic()
                control = create(controller.app)
                create_ms = max(0.0, self._monotonic() - started) * 1000.0
                started = self._monotonic()
                found = control is not None and bool(control.Exists(0))
                exists_ms = max(0.0, self._monotonic() - started) * 1000.0
                if debug_stage == "WAIT_EDITOR_EXPORT_BUTTON" and found:
                    # Write one completed-probe breakdown into the existing
                    # timeline; it performs no extra UIA query or polling.
                    self._trace(
                        "编辑页导出按钮定位性能",
                        f"窗口绑定={refresh_ms:.1f}ms；创建定位器={create_ms:.1f}ms；存在检查={exists_ms:.1f}ms；"
                        + "；".join(f"{name}={value:.1f}ms" for name, value in getattr(self, "_last_window_bind_timing", {}).items()),
                        stage=debug_stage, result="OK",
                    )
                if debug_stage:
                    controls = debug_controls(found) if debug_controls is not None else {label: found}
                    self._debug_wait(debug_stage, label, timeout_seconds, poll_count=poll_count, controls=controls)
                if not found:
                    if operation_id:
                        self._operation(
                            operation_id, operation_name_zh or label, "WAIT", operation_target or label,
                            "WAITING", poll_count=poll_count, current_result="尚未找到",
                        )
                    stable = 0
                    return False
                stable += 1
                if operation_id:
                    self._operation(
                        operation_id, operation_name_zh or label, "WAIT", operation_target or label,
                        "FOUND" if stable >= max(1, stable_samples) else "WAITING",
                        poll_count=poll_count, current_result="已找到",
                    )
                return stable >= max(1, stable_samples)
            except ExportFailure as exc:
                if exc.code == _TRANSIENT_WINDOW_TRANSITION:
                    stable = 0
                else:
                    raise
            except Exception:
                stable = 0
                if debug_stage:
                    controls = debug_controls(False) if debug_controls is not None else {label: False}
                    self._debug_wait(debug_stage, label, timeout_seconds, poll_count=poll_count, controls=controls)
                if operation_id:
                    self._operation(
                        operation_id, operation_name_zh or label, "WAIT", operation_target or label,
                        "WAITING", poll_count=poll_count, current_result="检测异常，继续等待",
                    )
                return False

        try:
            self._wait_until(label, available, timeout_seconds=timeout_seconds)
        except Exception as exc:
            if operation_id:
                self._operation(
                    operation_id, operation_name_zh or label, "WAIT", operation_target or label,
                    "FAILED", poll_count=poll_count, current_result=f"等待失败：{type(exc).__name__}",
                )
            raise
        return control

    def _debug_wait(
        self, stage: str, waiting_for: str, timeout_seconds: float, *, poll_count: int, controls: dict[str, bool],
    ) -> None:
        if stage == "WAIT_EDITOR_EXPORT_BUTTON":
            main_found = bool(controls.get("MainWindow"))
            button_found = bool(controls.get("MainWindowTitleBarExportBtn"))
            self._operation(
                "WAIT_MAIN_WINDOW", "等待剪辑窗口出现", "WAIT", "MainWindow（剪辑窗口）",
                "FOUND" if main_found else "WAITING", poll_count=poll_count,
                current_result="已出现" if main_found else "尚未出现",
            )
            self._operation(
                "FIND_EDITOR_EXPORT_BUTTON", "查找右上角「导出」按钮", "WAIT",
                "MainWindowTitleBarExportBtn（剪辑页导出按钮）",
                "FOUND" if button_found else "WAITING", poll_count=poll_count,
                current_result="已找到" if button_found else "尚未找到",
            )
        if stage == "WAIT_EXPORT_SETTINGS":
            window_found = bool(controls.get("Export Window"))
            group_found = bool(controls.get("Settings Group"))
            resolution_found = bool(controls.get("ExportSharpnessInput"))
            self._operation(
                "WAIT_EXPORT_WINDOW", "等待导出设置窗口", "WAIT", "ExportWindow（导出设置窗口）",
                "FOUND" if window_found else "WAITING", poll_count=poll_count,
                current_result="已出现" if window_found else "尚未出现",
            )
            self._operation(
                "FIND_SETTINGS_GROUP", "查找参数区域", "WAIT", "Settings Group（参数区域）",
                "FOUND" if group_found else "WAITING", poll_count=poll_count,
                current_result="已找到" if group_found else "尚未找到",
            )
            self._operation(
                "FIND_RESOLUTION_CONTROL", "查找分辨率设置", "WAIT", "ExportSharpnessInput（分辨率控件）",
                "FOUND" if resolution_found else "WAITING", poll_count=poll_count,
                current_result="已找到" if resolution_found else "尚未找到",
            )
        if self._debug_sink is None:
            return
        try:
            self._debug_sink({
                "stage": stage,
                "waiting_for": waiting_for,
                "timeout_seconds": timeout_seconds,
                "poll_count": poll_count,
                "controls": dict(controls),
            })
        except Exception:
            # Diagnostics are never allowed to change an export outcome.
            return

    def _wait_until(self, label: str, predicate: Callable[[], bool], *, timeout_seconds: float) -> None:
        deadline = self._monotonic() + timeout_seconds
        while True:
            if predicate():
                return
            if self._monotonic() >= deadline:
                raise ExportFailure("UI_CONDITION_TIMEOUT", f"等待{label}超过 {timeout_seconds:.0f} 秒")
            self._sleep(UI_POLL_SECONDS)

    @staticmethod
    def _read_current_parameter(control: Any, expected: str, *, allow_ocr: bool = True) -> str | None:
        """Read the currently displayed value, not just the requested value.

        Jianying exposes the input descriptor separately from its displayed
        value.  The value can be on the input itself or on a sibling in the
        same row, so inspect both locations and normalize only values from
        the expected resolution/FPS family.
        """
        expected_key = expected.casefold()
        known_values = _FRAMERATE_VALUES if expected_key.endswith("fps") else _RESOLUTION_VALUES
        candidates = [control]
        try:
            parent = control.GetParentControl()
            if parent is not None:
                candidates.extend(parent.GetChildren())
        except Exception:
            pass
        for candidate in candidates:
            for text in _control_texts(candidate):
                normalized = _normalize_parameter_text(text, known_values)
                if normalized is not None:
                    return normalized.casefold()
        return _read_parameter_value_from_screen(control, known_values) if allow_ocr else None

    def final_submit_clicked(self) -> None:
        # As soon as Jianying removes the final button, the surrounding
        # finally block releases the TopMost/input lease. Rendering is passive.
        deadline = self._monotonic() + 15.0
        self._operation_start("WAIT_EXPORT_ACCEPTED", "等待剪映接受导出", "WAIT", "ExportOkBtn（最终导出按钮消失）")
        while self._monotonic() < deadline:
            if not self._final_button_exists():
                if self.source_output_path is None or not self.source_output_path.is_absolute():
                    raise ExportFailure("UPSTREAM_SOURCE_PATH_UNREADABLE", "上游导出流程未回读唯一绝对 MP4 源路径")
                self._operation("WAIT_EXPORT_ACCEPTED", "等待剪映接受导出", "WAIT", "ExportOkBtn（最终导出按钮消失）", "DONE", current_result="剪映已接受导出")
                self._trace("最终导出已被剪映接受", stage="SUBMIT_EXPORT", result="OK")
                raise _SubmissionAccepted(self.source_output_path)
            self._operation("WAIT_EXPORT_ACCEPTED", "等待剪映接受导出", "WAIT", "ExportOkBtn（最终导出按钮消失）", "WAITING", current_result="最终按钮仍存在")
            self._sleep(.2)
        self._operation("WAIT_EXPORT_ACCEPTED", "等待剪映接受导出", "WAIT", "ExportOkBtn（最终导出按钮消失）", "FAILED", current_result="最终按钮未消失")
        raise ExportFailure("SUBMISSION_UNCONFIRMED", "最终导出后上游 ExportOkBtn 未消失；拒绝重复点击")

    def _trace(self, action: str, detail: str = "", *, stage: str = "", waiting_for: str = "", result: str = "", error: str = "") -> None:
        if self._trace_sink is None:
            return
        try:
            self._trace_sink({
                "action": action,
                "stage": stage,
                "started_at": time.time(),
                "waiting_for": waiting_for,
                "result": result,
                "error": error,
                "at": time.time(),
                "elapsed_ms": round(max(0.0, self._monotonic() - self._trace_started_at) * 1000.0, 1),
                "elapsed_seconds": round(max(0.0, self._monotonic() - self._trace_started_at), 3),
                "detail": detail,
            })
        except Exception:
            # Diagnostics must never change the export control path.
            pass

    def _remember_upstream_window(self, window: Any) -> None:
        if not any(window is item for item in self._upstream_windows):
            self._upstream_windows.append(window)

    def _release_upstream_topmost(self) -> None:
        # This adapter never sets TopMost.  The task only performs one normal
        # foreground handoff at acquisition, so there is no z-order lease to
        # revoke after submission.
        return

    def _final_button_exists(self) -> bool:
        try:
            control = self._raw_app.TextControl(searchDepth=2, Compare=lambda c, depth: depth == 2 and _description(c) == "ExportOkBtn")
            return bool(control.Exists(0))
        except Exception:
            return False


class PyJianyingUpstreamAdapter:
    """5.9 fact classifier plus the narrowly allowed post-submit additions."""

    def __init__(self, *, controller_type: type | None = None, uia: Any | None = None,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 foreground_guard_factory: Callable[[], ForegroundGuard] | None = None,
                 foreground_maximize: bool = True,
                 trace_sink: Callable[[dict[str, Any]], None] | None = None,
                 debug_sink: Callable[[dict[str, Any]], None] | None = None,
                 operation_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._controller_type, self._uia, self._sleep, self._monotonic = controller_type, uia, sleep, monotonic
        self._foreground_guard_factory = foreground_guard_factory or (lambda: _DefaultForegroundGuard(maximize=foreground_maximize))
        self._trace_sink = trace_sink
        self._debug_sink = debug_sink
        self._operation_sink = operation_sink
        self._trace_started_at = monotonic()
        self._active_pre_submit_guard: ForegroundGuard | None = None

    def preflight(self, request: ExportRequest) -> None:
        self._trace("导出器预检开始")
        if sys.platform != "win32": raise ExportFailure("WINDOWS_REQUIRED", "剪映 5.9 单份导出器只能在 Windows 桌面会话运行")
        try:
            import pyJianYingDraft as draft
            import uiautomation as uia
            from pyJianYingDraft.jianying_controller import ControlFinder
        except ImportError as exc:
            raise ExportFailure("DEPENDENCY_MISSING", f"缺少本机固定 Python 依赖：{exc.name}") from exc
        self._controller_type, self._uia = self._controller_type or draft.JianyingController, self._uia or uia
        if not (request.output_directory / ".").is_dir(): raise ExportFailure("OUTPUT_DIRECTORY_MISSING", "独立测试输出目录不可用")
        if request.apply_export_parameters and request.allow_parameter_ocr:
            _warm_local_ocr()
        self._trace("导出器预检完成")

    def begin_pre_submit(self) -> None:
        if self._active_pre_submit_guard is None:
            self._trace("接管键鼠并置前剪映")
            self._active_pre_submit_guard = self._foreground_guard_factory()
            self._active_pre_submit_guard.acquire()
            self._trace("剪映已置前，开始识别页面")

    def open_draft_only(self, draft_name: str) -> None:
        """Open one exact home-page draft using the production export locator.

        This intentionally stops at the editor page.  It shares the exporter's
        ValuePattern search, exact title match, safe-card bounds check and
        foreground lease instead of introducing a second Jianying opener.
        """
        if sys.platform != "win32":
            raise ExportFailure("WINDOWS_REQUIRED", "剪映 5.9 草稿只能在 Windows 桌面会话打开")
        try:
            import pyJianYingDraft as draft
            import uiautomation as uia
        except ImportError as exc:
            raise ExportFailure("DEPENDENCY_MISSING", f"缺少本机固定 Python 依赖：{exc.name}") from exc
        self._controller_type, self._uia = self._controller_type or draft.JianyingController, self._uia or uia
        self.begin_pre_submit()
        try:
            from server.windows_automation.jianying59_exporter.executor import SingleDraftExporter
            SingleDraftExporter(self).prepare_and_open_named_draft(draft_name)
        finally:
            self.release_pre_submit()

    def open_named_draft(self, draft_name: str) -> None:
        """Open one draft while the caller owns the active foreground lease."""
        from pyJianYingDraft.jianying_controller import ControlFinder
        session = PassiveUpstreamController(
            self._controller_type,
            uia=self._uia,
            foreground_guard=self._active_pre_submit_guard,
        )
        controller = session._controller_type()
        session._open_draft_until_editor(controller, draft_name, ControlFinder)

    def release_pre_submit(self) -> None:
        guard, self._active_pre_submit_guard = self._active_pre_submit_guard, None
        if guard is not None:
            guard.release()

    def inspect_page(self) -> JianyingPage:
        self._trace("开始识别当前剪映页面")
        page = self._inspect(passive=True)
        self._trace("当前剪映页面已识别", page.value)
        return page
    def observe_page_passively(self) -> JianyingPage: return self._inspect(passive=True)

    def _operation_guard(self) -> tuple[ForegroundGuard, bool]:
        if self._active_pre_submit_guard is not None:
            return self._active_pre_submit_guard, False
        guard = self._foreground_guard_factory()
        guard.acquire()
        return guard, True

    @staticmethod
    def _release_operation_guard(guard: ForegroundGuard, owned: bool) -> None:
        if owned:
            guard.release()

    def return_edit_to_home(self) -> None:
        guard, owned = self._operation_guard()
        try:
            session = PassiveUpstreamController(
                self._controller_type, uia=self._uia, foreground_guard=guard,
            )
            controller = session._controller_type()
            if getattr(controller, "app_status", None) != "edit":
                raise ExportFailure("EDIT_RECOVERY_UNAVAILABLE", "当前页面不是可返回首页的剪辑页")
            close = controller.app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
            if not close.Exists(0):
                raise ExportFailure("HOME_RECOVERY_UNAVAILABLE", "编辑页没有唯一返回首页控件")
            close.Click(simulateMove=False)
            self._wait_for_controller_state(controller, "home", "返回首页", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS)
        finally:
            self._release_operation_guard(guard, owned)

    def close_unsubmitted_parameter_dialog(self) -> bool:
        guard, owned = self._operation_guard()
        try:
            session = PassiveUpstreamController(
                self._controller_type, uia=self._uia, foreground_guard=guard,
            )
            controller = session._controller_type()
            if getattr(controller, "app_status", None) != "pre_export":
                return False
            if self._uia is not None:
                dialog = self._uia.WindowControl(
                    searchDepth=2, searchInterval=0, AutomationId="ExportWindow_Container",
                )
            else:
                window_factory = getattr(controller.app, "WindowControl", None)
                if not callable(window_factory):
                    raise ExportFailure("PARAMETER_DIALOG_CLOSE_UNAVAILABLE", "当前剪映页面不支持定位导出参数窗")
                dialog = window_factory(
                    searchDepth=1, searchInterval=0, AutomationId="ExportWindow_Container",
                )
            if dialog is None or not dialog.Exists(0):
                raise ExportFailure("PARAMETER_DIALOG_CLOSE_UNAVAILABLE", "未找到可关闭的剪映导出参数窗")
            window_pattern = dialog.GetWindowPattern()
            if window_pattern is None or not window_pattern.Close():
                raise ExportFailure("PARAMETER_DIALOG_CLOSE_UNAVAILABLE", "剪映导出参数窗拒绝关闭")
            self._wait_for_controller_state(controller, "edit", "关闭导出参数页", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS)
            return True
        finally:
            self._release_operation_guard(guard, owned)

    def submit_with_upstream_controller(self, request: ExportRequest) -> PersistentSubmission:
        guard, owned = self._operation_guard()
        try:
            source = PassiveUpstreamController(
                self._controller_type, uia=self._uia, sleep=self._sleep, monotonic=self._monotonic,
                foreground_guard=guard, trace_sink=self._trace_sink, debug_sink=self._debug_sink,
                operation_sink=self._operation_sink,
            ).export_until_submission(request)
            return PersistentSubmission(request.draft_name, str(source), str(request.expected_output_path), time.time())
        finally:
            if self._active_pre_submit_guard is guard:
                self._active_pre_submit_guard = None
            elif owned:
                guard.release()

    def close_success_and_return_home(self) -> None:
        guard, owned = self._operation_guard()
        try:
            self._trace("开始关闭导出成功页并返回首页")
            session = PassiveUpstreamController(
                self._controller_type, uia=self._uia, foreground_guard=guard,
            )
            controller = session._controller_type()
            if getattr(controller, "app_status", None) != "pre_export":
                raise ExportFailure("SUCCESS_CLEANUP_UNAVAILABLE", "当前不是上游识别的导出成功页")
            close = controller.app.TextControl(searchDepth=2, Compare=lambda c, depth: depth == 2 and _description(c) == "ExportSucceedCloseBtn")
            if not close.Exists(0): raise ExportFailure("SUCCESS_PAGE_UNCONFIRMED", "导出页没有唯一成功关闭控件")
            close.Click(simulateMove=False)
            self._wait_for_controller_state(controller, "edit", "成功页关闭后返回编辑页", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS)
            close = controller.app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
            if not close.Exists(0): raise ExportFailure("HOME_RECOVERY_UNAVAILABLE", "编辑页没有唯一返回首页控件")
            close.Click(simulateMove=False)
            self._wait_for_controller_state(controller, "home", "成功页关闭后返回首页", OPEN_EXPORT_DIALOG_TIMEOUT_SECONDS)
            self._trace("导出成功页已返回首页")
        finally:
            self._release_operation_guard(guard, owned)

    def _trace(self, action: str, detail: str = "") -> None:
        if self._trace_sink is None:
            return
        self._trace_sink({
            "action": action,
            "at": self._monotonic(),
            "elapsed_seconds": round(max(0.0, self._monotonic() - self._trace_started_at), 3),
            "detail": detail,
        })

    def _wait_for_controller_state(self, controller: Any, expected: str, label: str, timeout_seconds: float) -> None:
        deadline = self._monotonic() + timeout_seconds
        while True:
            try:
                controller.get_window()
                if getattr(controller, "app_status", None) == expected:
                    return
            except Exception:
                pass
            if self._monotonic() >= deadline:
                raise ExportFailure("HOME_RECOVERY_UNCONFIRMED", f"等待{label}超过 {timeout_seconds:.0f} 秒")
            self._sleep(UI_POLL_SECONDS)

    def _inspect(self, *, passive: bool) -> JianyingPage:
        if self._uia is None: raise ExportFailure("PREFLIGHT_REQUIRED", "必须先完成固定依赖预检")
        root = self._uia.GetRootControl()
        matches = [control for control, depth in self._uia.WalkControl(root, maxDepth=2)
                   if depth > 0 and str(getattr(control, "Name", "")) == APP_NAME and str(getattr(control, "AutomationId", "")) in {"HomeWindow", "MainWindow"}]
        editors = [control for control in matches if str(getattr(control, "AutomationId", "")) == "MainWindow"]
        homes = [control for control in matches if str(getattr(control, "AutomationId", "")) == "HomeWindow"]
        if len(editors) == 1:
            main = editors[0]
        elif not editors and len(homes) == 1:
            main = homes[0]
        else:
            return JianyingPage.UNKNOWN
        facts = _facts(main, self._uia)
        if str(getattr(main, "AutomationId", "")) == "HomeWindow" and not facts["dialog"]: return JianyingPage.HOME
        if str(getattr(main, "AutomationId", "")) != "MainWindow": return JianyingPage.UNKNOWN
        if facts["success"]: return JianyingPage.SUCCESS_PAGE
        if facts["dialog"] and facts["final"]: return JianyingPage.PARAMETER_DIALOG
        if facts["dialog"]: return JianyingPage.EXPORTING
        return JianyingPage.EDIT


def _facts(main: Any, uia: Any) -> dict[str, bool]:
    controls = [control for control, depth in uia.WalkControl(main, maxDepth=5) if depth > 0]
    return {"dialog": any(str(getattr(c, "AutomationId", "")) == "ExportWindow_Container" for c in controls), "final": any(_description(c) == "ExportOkBtn" for c in controls), "success": any(_description(c) == "ExportSucceedCloseBtn" for c in controls)}


def _description(control: Any) -> str:
    try: return str(control.GetPropertyValue(DESCRIPTION_PROPERTY) or "").strip()
    except Exception: return ""


def _control_rect(control: Any) -> tuple[float, float, float, float] | None:
    try:
        rect = getattr(control, "BoundingRectangle")
        values = (float(rect.left), float(rect.top), float(rect.right), float(rect.bottom))
    except (AttributeError, TypeError, ValueError):
        try:
            values = tuple(float(value) for value in getattr(control, "BoundingRectangle"))
        except (AttributeError, TypeError, ValueError):
            return None
    left, top, right, bottom = values
    return (left, top, right, bottom) if right > left and bottom > top else None


def _rect_contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _rect_center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)


def _control_offscreen(control: Any) -> bool:
    try:
        return bool(getattr(control, "IsOffscreen"))
    except (AttributeError, TypeError):
        return False


def _control_texts(control: Any) -> tuple[str, ...]:
    values: list[str] = []
    for attribute in ("Name", "Value"):
        try:
            value = str(getattr(control, attribute) or "").strip()
        except Exception:
            value = ""
        if value:
            values.append(value)
    for property_id in (NAME_PROPERTY, VALUE_PROPERTY, DESCRIPTION_PROPERTY):
        try:
            value = str(control.GetPropertyValue(property_id) or "").strip()
        except Exception:
            value = ""
        if value:
            values.append(value)
    return tuple(values)


def _normalize_parameter_text(value: str, known_values: tuple[str, ...]) -> str | None:
    """Map UI labels such as ``1080p`` or ``30 fps`` to canonical values."""
    compact = re.sub(r"\s+", "", str(value)).casefold()
    for known in known_values:
        if known.casefold() in compact:
            return known
    return None


def _read_parameter_value_from_screen(control: Any, known_values: tuple[str, ...]) -> str | None:
    """OCR only the parameter's current screen rectangle when UIA is empty."""
    try:
        rectangle = control.BoundingRectangle
        left, top, right, bottom = (int(rectangle.left), int(rectangle.top), int(rectangle.right), int(rectangle.bottom))
        if right <= left or bottom <= top:
            return None
        from PIL import ImageGrab
        frame = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        for text, confidence in _local_ocr(frame):
            normalized = _normalize_parameter_text(text, known_values)
            if normalized is not None and confidence >= OCR_MINIMUM_CONFIDENCE:
                return normalized.casefold()
    except Exception:
        return None
    return None


def _local_ocr(frame: Any) -> tuple[tuple[str, float], ...]:
    global _OCR_ENGINE
    try:
        _warm_local_ocr()
        if _OCR_ENGINE is None:
            return ()
        result, _elapsed = _OCR_ENGINE(frame)
    except Exception:
        return ()
    return tuple((str(text), float(confidence)) for _box, text, confidence in result or ())


def _warm_local_ocr() -> None:
    """Load the local OCR model before it can block a visible export dialog."""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return
    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    except Exception:
        # UIA may still expose the value, so retain the existing fail-closed
        # behavior only if neither read path can provide it later.
        return
