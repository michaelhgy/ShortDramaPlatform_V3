"""Windows-only observation and calibrated-input boundaries for V1 Jianying.

No queue state lives here. The executor owns task/session transitions; this
module only captures evidence, locates V1 anchors, and refuses input unless a
caller supplies an active input lease.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .export_automation import AnchorLocator, ExportAction, ExportAutomationError, InputActuator, LocatorCandidate, PageCheck, PageObserver, PageSnapshot


PROFILE_VERSION = 1
DEFAULT_MINIMUM_SCORE = 0.82
_V1_AUTOMATION_INPUT_MARKER = 0x53445031


class JianyingAdapterError(RuntimeError):
    """The local Jianying surface is not safe to observe or act on."""


@dataclass(frozen=True)
class JianyingWindow:
    handle: int
    title: str
    pid: int
    executable: str
    rect: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]


def _select_jianying_main_window(
    candidates: Sequence[JianyingWindow], *, uia_roles: Mapping[int, str] | None = None
) -> JianyingWindow:
    """Prefer the localized Jianying main window over a transient Qt container."""
    localized = [window for window in candidates if window.title == "剪映专业版"]
    if len(localized) == 1:
        return localized[0]
    if len(localized) > 1:
        # The editor creates auxiliary top-level Qt windows with the same
        # localized title. The actual work surface is deterministically the
        # largest verified Jianying window; fail only if two candidates are
        # genuinely the same size.
        ranked = sorted(localized, key=lambda window: window.width * window.height, reverse=True)
        if len(ranked) == 1 or ranked[0].width * ranked[0].height > ranked[1].width * ranked[1].height:
            return ranked[0]
        # Jianying 5.9 keeps its HomeWindow alive while the editor is open.
        # Those two top-level Qt windows can have the same title and size, but
        # UIA exposes their stable roles. Prefer only a unique editor surface.
        editor_windows = [window for window in localized if (uia_roles or {}).get(window.handle) == "MainWindow"]
        if len(editor_windows) == 1:
            return editor_windows[0]
        raise JianyingAdapterError(f"未找到唯一可用的剪映主窗口，当前数量：{len(localized)}")
    if len(candidates) != 1:
        raise JianyingAdapterError(f"未找到唯一可用的剪映主窗口，当前数量：{len(candidates)}")
    return candidates[0]


def calibration_profile_path(data_root: Path) -> Path:
    return data_root / "calibration" / "jianying" / "main.json"


def _modules() -> tuple[Any, Any, tuple[Any, Any, Any, Any, Any], Any, Any]:
    if os.name != "nt":
        raise JianyingAdapterError("V1 剪映视觉适配器只能在 Windows 上运行")
    try:
        import cv2
        import numpy as np
        import win32api
        import win32con
        import win32gui
        import win32process
        import win32ui
        from PIL import Image, ImageGrab
    except ImportError as exc:  # pragma: no cover - depends on the local machine
        raise JianyingAdapterError(f"缺少 V1 剪映视觉适配依赖：{exc}") from exc
    return cv2, np, (win32api, win32con, win32gui, win32process, win32ui), Image, ImageGrab


def _dpi_aware() -> None:
    try:  # pragma: no cover - Windows API behavior
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _process_path(win32api: Any, win32con: Any, win32process: Any, pid: int) -> str:
    handle = None
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return str(win32process.GetModuleFileNameEx(handle, 0))
    except Exception:
        return ""
    finally:
        if handle:
            win32api.CloseHandle(handle)


def _jianying_uia_window_roles() -> dict[int, str]:
    """Map top-level 5.9 UIA roles to native window handles when available."""
    try:
        import uiautomation as uia
        roles: dict[int, str] = {}
        for control, depth in uia.WalkControl(uia.GetRootControl(), maxDepth=2):
            if depth <= 0:
                continue
            role = str(getattr(control, "AutomationId", "") or "")
            if role not in {"HomeWindow", "MainWindow"}:
                continue
            handle = int(control.GetPropertyValue(30020) or 0)
            if handle:
                roles[handle] = role
        return roles
    except Exception:
        # UIA is an optional discriminator. The normal title/size checks stay
        # fail-closed when its evidence is absent or ambiguous.
        return {}


def discover_jianying_window() -> JianyingWindow:
    """Find exactly one top-level Jianying main window or fail closed."""
    _dpi_aware()
    _cv2, _np, modules, _Image, _ImageGrab = _modules()
    win32api, win32con, win32gui, win32process, _win32ui = modules
    matches: list[JianyingWindow] = []

    def collect(hwnd: int, _param: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = str(win32gui.GetWindowText(hwnd) or "")
        if title not in {"剪映专业版", "JianyingPro"}:
            return True
        if win32gui.GetParent(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        executable = _process_path(win32api, win32con, win32process, int(pid))
        if "jianyingpro.exe" not in executable.casefold():
            return True
        rect = tuple(int(value) for value in win32gui.GetWindowRect(hwnd))
        if not win32gui.IsIconic(hwnd) and (rect[2] - rect[0] < 900 or rect[3] - rect[1] < 600):
            return True
        # A minimized Jianying main window is commonly reported as invisible.
        # Keep it as a candidate so foreground_jianying_window can restore and
        # maximize the exact verified window before any UI input is sent.
        matches.append(JianyingWindow(int(hwnd), title, int(pid), executable, rect))
        return True

    win32gui.EnumWindows(collect, None)
    return _select_jianying_main_window(matches, uia_roles=_jianying_uia_window_roles())


def _wait_for_jianying_window(
    *, timeout_seconds: float = 10.0, sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> JianyingWindow:
    """Wait through Jianying 5.9's short top-level-window recreation."""
    deadline = monotonic() + timeout_seconds
    last_error: JianyingAdapterError | None = None
    while True:
        try:
            return discover_jianying_window()
        except JianyingAdapterError as exc:
            last_error = exc
            if monotonic() >= deadline:
                raise last_error
            sleep(0.2)


def foreground_jianying_window(*, maximize: bool = True) -> JianyingWindow:
    """Bring the verified Jianying window forward once, optionally maximizing."""
    window = _wait_for_jianying_window()
    _cv2, _np, modules, _Image, _ImageGrab = _modules()
    _win32api, win32con, win32gui, win32process, _win32ui = modules
    errors: list[str] = []

    def request_foreground() -> bool:
        try:
            if maximize:
                win32gui.ShowWindow(window.handle, win32con.SW_MAXIMIZE)
            # Jianying may report the restored rectangle for a short period
            # while its QML surface is being reparented.
            time.sleep(0.12)
            win32gui.BringWindowToTop(window.handle)
            win32gui.SetForegroundWindow(window.handle)
        except Exception as exc:
            errors.append(str(exc))
        return int(win32gui.GetForegroundWindow() or 0) == window.handle

    if not request_foreground():
        # A server request runs on a non-UI thread, so joining only the current
        # foreground and Jianying threads is not always enough.  Temporarily
        # join the current request thread too, then retry all normal window
        # activation APIs.  No mouse or keyboard event is synthesized here.
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
        user32.AttachThreadInput.restype = ctypes.c_bool
        foreground = int(win32gui.GetForegroundWindow() or 0)
        foreground_thread = int(win32process.GetWindowThreadProcessId(foreground)[0]) if foreground else 0
        target_thread = int(win32process.GetWindowThreadProcessId(window.handle)[0])
        current_thread = int(kernel32.GetCurrentThreadId())
        attached: list[tuple[int, int]] = []
        try:
            # Allowing foreground activation is advisory; the final focus check
            # below remains the only condition that permits automation.
            try:
                user32.AllowSetForegroundWindow(0xFFFFFFFF)
            except Exception:
                pass
            for source, target in ((foreground_thread, target_thread), (current_thread, foreground_thread), (current_thread, target_thread)):
                if source and target and source != target and bool(user32.AttachThreadInput(source, target, True)):
                    attached.append((source, target))
            request_foreground()
        finally:
            for source, target in reversed(attached):
                try:
                    user32.AttachThreadInput(source, target, False)
                except Exception:
                    pass
    if int(win32gui.GetForegroundWindow() or 0) != window.handle:
        try:
            # Unlike SetForegroundWindow, this legacy window-manager request
            # explicitly asks Windows to switch to the target task. It is used
            # only after the normal APIs have failed, and still requires the
            # exact foreground-window proof below.
            user32 = ctypes.windll.user32
            user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
            user32.SwitchToThisWindow.restype = None
            user32.SwitchToThisWindow(window.handle, True)
            time.sleep(0.08)
        except Exception as exc:
            errors.append(str(exc))
    if int(win32gui.GetForegroundWindow() or 0) != window.handle:
        detail = "；".join(dict.fromkeys(errors)) or "Windows 前台焦点锁阻止请求"
        raise JianyingAdapterError(f"剪映窗口未获得前台焦点，已停止后续自动化：{detail}")
    return _wait_for_jianying_window()


def machine_fingerprint(window: JianyingWindow) -> dict[str, Any]:
    try:
        dpi = int(ctypes.windll.user32.GetDpiForWindow(window.handle))
    except Exception:  # pragma: no cover
        dpi = 96
    try:
        mtime = Path(window.executable).stat().st_mtime_ns
    except OSError:
        mtime = None
    return {
        "windows_version": platform.version(),
        "jianying_executable": window.executable,
        "jianying_executable_mtime_ns": mtime,
        "dpi": dpi,
        "window_size": [window.width, window.height],
    }


def read_profile(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JianyingAdapterError(f"无法读取 V1 剪映校准档案：{path}（{exc}）") from exc
    if not isinstance(payload, dict) or payload.get("profile_version") != PROFILE_VERSION:
        raise JianyingAdapterError("V1 剪映校准档案版本不受支持")
    return payload


def write_profile(path: Path, payload: dict[str, Any]) -> None:
    """Atomically store a machine-local V1 calibration profile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def calibration_health(path: Path, required_anchors: Sequence[str] = ()) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "ready": False, "reason": "missing_profile", "anchors": []}
    try:
        profile = read_profile(path)
    except JianyingAdapterError as exc:
        return {"path": str(path), "ready": False, "reason": str(exc), "anchors": []}
    anchors = profile.get("anchors") if isinstance(profile.get("anchors"), dict) else {}
    required = tuple(required_anchors) or tuple(anchors)
    entries: list[dict[str, Any]] = []
    for key in required:
        item = anchors.get(key) if isinstance(anchors.get(key), dict) else {}
        sample = Path(str(item.get("sample", ""))) if item.get("sample") else None
        sampled = bool(item.get("reference_from") == "v1_guided_capture" and sample and sample.is_file())
        visual_verified = bool(item.get("visual_verified_at"))
        action_tested = bool(item.get("last_action_test"))
        fully_verified = bool(
            item.get("page")
            and item.get("verified_at")
            and sampled
            and visual_verified
            and action_tested
            and isinstance(item.get("search_region"), dict)
            and isinstance(item.get("click_offset"), dict)
        )
        entries.append({
            "key": key,
            "ready": fully_verified,
            "fully_verified": fully_verified,
            "sampled": sampled,
            "visual_verified": visual_verified,
            "action_tested": action_tested,
            "verified_at": item.get("verified_at"),
        })
    ready = bool(entries) and all(item["ready"] for item in entries)
    return {"path": str(path), "ready": ready, "reason": "" if ready else "anchors_unverified", "anchors": entries, "machine_fingerprint": profile.get("machine_fingerprint") or {}}


class WindowsJianyingObserver(PageObserver):
    """Capture one Jianying surface into the per-session evidence directory."""

    def __init__(self, evidence_root: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.evidence_root = evidence_root
        self.clock = clock

    def capture(self) -> PageSnapshot:
        window = discover_jianying_window()
        frame, capture_strategy, capture_rect = self._capture(window)
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        target = self.evidence_root / f"page-{int(self.clock() * 1000)}-{time.monotonic_ns()}.png"
        cv2, _np, _modules_value, _Image, _ImageGrab = _modules()
        encoded, image = cv2.imencode(".png", frame)
        if not encoded:
            raise JianyingAdapterError(f"无法保存剪映页面证据：{target}")
        target.write_bytes(image.tobytes())
        return PageSnapshot(str(window.handle), self.clock(), str(target), {
            "title": window.title,
            "pid": window.pid,
            "rect": list(capture_rect),
            "owner_rect": list(window.rect),
            "capture_strategy": capture_strategy,
            "fingerprint": machine_fingerprint(window),
        })

    def check(self, snapshot: PageSnapshot, condition: str) -> PageCheck:
        return PageCheck(condition, False, {"screenshot_path": snapshot.screenshot_path, "reason": "需要经过校准的页面条件"})

    @staticmethod
    def _capture(window: JianyingWindow):
        cv2, np, modules, Image, ImageGrab = _modules()
        _win32api, _win32con, win32gui, _win32process, win32ui = modules
        dialog = WindowsJianyingObserver._find_composited_dialog(window)
        if dialog is not None:
            handle, rect = dialog
            frame = WindowsJianyingObserver._capture_handle(handle, rect, cv2, np, Image, win32gui, win32ui)
            if frame is not None and float(frame.std()) > 2.0:
                return frame, "print_window_child_dialog", rect
        source_dc = win32gui.GetWindowDC(window.handle)
        source = win32ui.CreateDCFromHandle(source_dc)
        memory = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, window.width, window.height)
            memory.SelectObject(bitmap)
            rendered = bool(ctypes.windll.user32.PrintWindow(window.handle, memory.GetSafeHdc(), 2))
            if rendered:
                raw = bitmap.GetBitmapBits(True)
                image = Image.frombuffer("RGB", (window.width, window.height), raw, "raw", "BGRX", 0, 1)
                window_frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
                if float(window_frame.std()) > 2.0:
                    # Export settings are rendered in a composited Qt layer on
                    # Jianying 11.2.  PrintWindow returns only the dimmed owner
                    # surface in that state, while a desktop capture contains
                    # the real dialog.  Prefer it only when the central change
                    # is large enough to be a dialog, not ordinary animation.
                    screen_frame = WindowsJianyingObserver._screen_capture(ImageGrab, cv2, np, window)
                    if WindowsJianyingObserver._has_composited_modal(window_frame, screen_frame, cv2, np):
                        return screen_frame, "screen_composited_modal", window.rect
                    return window_frame, "print_window", window.rect
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            memory.DeleteDC()
            source.DeleteDC()
            win32gui.ReleaseDC(window.handle, source_dc)
        return WindowsJianyingObserver._screen_capture(ImageGrab, cv2, np, window), "screen_fallback", window.rect

    @staticmethod
    def _find_composited_dialog(window: JianyingWindow) -> tuple[int, tuple[int, int, int, int]] | None:
        """Return the active Jianying modal surface without matching its title text.

        The title includes the draft name and must never become a locator.  UIA
        is used solely to obtain the native child handle and bounds; visual
        anchors remain responsible for page identity and actions.
        """
        try:
            import uiautomation as auto
            root = auto.ControlFromHandle(window.handle)
            for child in root.GetChildren():
                handle = int(child.NativeWindowHandle or 0)
                rect = child.BoundingRectangle
                left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
                width, height = right - left, bottom - top
                if not handle or handle == window.handle or width < 300 or height < 250:
                    continue
                if left < window.rect[0] or top < window.rect[1] or right > window.rect[2] or bottom > window.rect[3]:
                    continue
                # Jianying's main QML children identify themselves as
                # JianyingPro; the export surface has a draft-derived title.
                if str(child.Name or "") == "JianyingPro":
                    continue
                return handle, (left, top, right, bottom)
        except Exception:
            return None
        return None

    @staticmethod
    def _capture_handle(handle: int, rect: tuple[int, int, int, int], cv2: Any, np: Any, Image: Any, win32gui: Any, win32ui: Any):
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        source_dc = win32gui.GetWindowDC(handle)
        source = win32ui.CreateDCFromHandle(source_dc)
        memory = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, width, height)
            memory.SelectObject(bitmap)
            if not bool(ctypes.windll.user32.PrintWindow(handle, memory.GetSafeHdc(), 2)):
                return None
            raw = bitmap.GetBitmapBits(True)
            image = Image.frombuffer("RGB", (width, height), raw, "raw", "BGRX", 0, 1)
            return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            memory.DeleteDC()
            source.DeleteDC()
            win32gui.ReleaseDC(handle, source_dc)

    @staticmethod
    def _screen_capture(ImageGrab: Any, cv2: Any, np: Any, window: JianyingWindow):
        image = ImageGrab.grab(bbox=window.rect, all_screens=True)
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _has_composited_modal(window_frame: Any, screen_frame: Any, cv2: Any, np: Any) -> bool:
        if window_frame.shape != screen_frame.shape:
            return False
        height, width = window_frame.shape[:2]
        if height < 200 or width < 300:
            return False
        # Ignore title bars and edges.  A modal must reveal a meaningful,
        # connected brighter surface in the central Jianying client area.
        top, bottom = round(height * .12), round(height * .82)
        left, right = round(width * .12), round(width * .88)
        delta = cv2.cvtColor(screen_frame, cv2.COLOR_BGR2GRAY).astype(np.int16) - cv2.cvtColor(window_frame, cv2.COLOR_BGR2GRAY).astype(np.int16)
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[top:bottom, left:right] = (delta[top:bottom, left:right] >= 34).astype(np.uint8) * 255
        count, _labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
        minimum_area = max(4000, round(width * height * .012))
        return any(int(stats[index, cv2.CC_STAT_AREA]) >= minimum_area for index in range(1, count))


class V1PageObserver(WindowsJianyingObserver):
    """Checks page identity from required, calibrated visual anchors."""

    _PAGE_REQUIREMENTS = {
        "DRAFT_HOME": ("home_tab",),
        "DRAFT_SEARCH": ("search_input",),
        "DRAFT_SEARCH_RESULTS": ("search_input", "result_open_area"),
        "EDITOR": ("editor_export",),
        "EXPORT_DIALOG": ("title", "output_path", "resolution_dropdown", "fps_dropdown", "final_export"),
        "RESOLUTION_MENU": ("resolution_1080p",),
        "EXPORT_DIALOG_1080P_SELECTED": ("resolution_1080p_selected",),
        "FPS_MENU": ("fps_30",),
        "EXPORT_DIALOG_FPS_30_SELECTED": ("fps_30_selected",),
        "EXPORT_READY": ("resolution_1080p_selected", "fps_30_selected", "final_export"),
        "EXPORTING": ("exporting_status",),
        "EXPORT_SUCCESS": ("export_success_close",),
        "HOME_AFTER_COLLAPSE": ("home_tab",),
    }

    def __init__(self, evidence_root: Path, calibration_profile: Path, *, clock: Callable[[], float] = time.time) -> None:
        super().__init__(evidence_root, clock=clock)
        self.locator = V1AnchorLocator(calibration_profile)

    def check(self, snapshot: PageSnapshot, condition: str) -> PageCheck:
        required = self._PAGE_REQUIREMENTS.get(condition)
        if required is None:
            return PageCheck(condition, False, {"screenshot_path": snapshot.screenshot_path, "reason": "unknown_page_condition"})
        results: list[dict[str, Any]] = []
        matched = True
        for locator in required:
            candidates = self.locator.locate(snapshot, locator)
            candidate = candidates[0] if len(candidates) == 1 else None
            threshold = float(candidate.evidence.get("threshold", DEFAULT_MINIMUM_SCORE)) if candidate else DEFAULT_MINIMUM_SCORE
            passed = candidate is not None and candidate.score >= threshold
            matched = matched and passed
            results.append({"locator": locator, "matched": passed, "score": candidate.score if candidate else None, "threshold": threshold})
        return PageCheck(condition, matched, {"screenshot_path": snapshot.screenshot_path, "strategy": "calibrated_visual_anchors", "anchors": results})

    def wait_for_stable(self, condition: str, *, stable_seconds: float, timeout_seconds: float) -> dict[str, Any]:
        """Require a calibrated page condition on two fresh captures.

        Jianying can expose a control while its QML content or media preview is
        still settling.  This is intentionally visual evidence, not a blind
        sleep: any failed capture restarts the stability window.
        """
        if stable_seconds < 0 or timeout_seconds <= 0:
            raise ValueError("页面稳定等待参数无效")
        started = time.monotonic()
        first: PageSnapshot | None = None
        checks: list[dict[str, Any]] = []
        while time.monotonic() - started <= timeout_seconds:
            snapshot = self.capture()
            page = self.check(snapshot, condition)
            checks.append({
                "screenshot_path": snapshot.screenshot_path,
                "matched": page.matched,
                "anchors": page.evidence.get("anchors", []),
            })
            if not page.matched:
                first = None
                time.sleep(0.25)
                continue
            if first is None:
                first = snapshot
                if stable_seconds:
                    time.sleep(stable_seconds)
                continue
            return {
                "stable_seconds": stable_seconds,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "first_screenshot_path": first.screenshot_path,
                "last_screenshot_path": snapshot.screenshot_path,
                "checks": checks,
            }
        raise JianyingAdapterError(f"页面条件 {condition} 未连续稳定")


class V1AnchorLocator(AnchorLocator):
    """Locate one calibrated anchor in its bounded local search area."""

    def __init__(self, calibration_profile: Path) -> None:
        self.calibration_profile = calibration_profile

    def locate(self, snapshot: PageSnapshot, locator: str) -> Sequence[LocatorCandidate]:
        profile = read_profile(self.calibration_profile)
        anchor = (profile.get("anchors") or {}).get(locator)
        if not isinstance(anchor, dict):
            return []
        screenshot, sample = Path(snapshot.screenshot_path), Path(str(anchor.get("sample", "")))
        if not screenshot.is_file() or not sample.is_file():
            return []
        cv2, np, _modules_value, _Image, _ImageGrab = _modules()
        frame = cv2.imdecode(np.frombuffer(screenshot.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        template = cv2.imdecode(np.frombuffer(sample.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        region = anchor.get("search_region") or {}
        try:
            left, top, width, height = (int(region[key]) for key in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError):
            return []
        if frame is None or template is None or width <= 0 or height <= 0:
            return []
        # Calibration captures are machine-local and may have been taken at a
        # different DPI or maximized client size. Scale both the bounded search
        # region and the sample before matching; never reuse stale desktop
        # pixels as absolute coordinates.
        fingerprint = profile.get("machine_fingerprint") if isinstance(profile.get("machine_fingerprint"), dict) else {}
        calibrated_size = fingerprint.get("window_size") if isinstance(fingerprint.get("window_size"), list) else None
        current_size = snapshot.metadata.get("owner_rect") or snapshot.metadata.get("rect") or []
        try:
            calibrated_width, calibrated_height = int(calibrated_size[0]), int(calibrated_size[1])
            current_width = int(current_size[2]) - int(current_size[0])
            current_height = int(current_size[3]) - int(current_size[1])
            sx = current_width / calibrated_width if calibrated_width > 0 else 1.0
            sy = current_height / calibrated_height if calibrated_height > 0 else 1.0
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            sx = sy = 1.0
        sx = min(3.0, max(0.5, sx))
        sy = min(3.0, max(0.5, sy))
        left, top = round(left * sx), round(top * sy)
        width, height = round(width * sx), round(height * sy)
        if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
            template = cv2.resize(template, None, fx=sx, fy=sy, interpolation=cv2.INTER_CUBIC)
        search = frame[top : top + height, left : left + width]
        if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
            return []
        _min, score, _min_loc, point = cv2.minMaxLoc(cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED))
        offset = anchor.get("click_offset") or {}
        rect = snapshot.metadata.get("rect") or [0, 0, 0, 0]
        x = int(rect[0]) + left + point[0] + round(int(offset.get("x", 0)) * sx)
        y = int(rect[1]) + top + point[1] + round(int(offset.get("y", 0)) * sy)
        return [LocatorCandidate(locator, x, y, float(score), "visual_anchor_scaled", {"sample": str(sample), "scale": {"x": sx, "y": sy}, "search_region": {"x": left, "y": top, "width": width, "height": height}, "screenshot_path": str(screenshot), "threshold": float(anchor.get("threshold", DEFAULT_MINIMUM_SCORE))})]


class LeaseGuardedWindowsActuator(InputActuator):
    """Inject a single click only while the V1 input lease remains active."""

    def __init__(self, lease_is_active: Callable[[], bool]) -> None:
        self.lease_is_active = lease_is_active

    def perform(self, action: ExportAction, candidate: LocatorCandidate) -> dict[str, Any]:
        if not self.lease_is_active():
            raise ExportAutomationError("INPUT_LEASE_REQUIRED", "未获得活动键鼠接管，拒绝执行剪映点击")
        if action.input_kind == "verify":
            return {
                "input": "verify",
                "action_id": action.action_id,
                "point": {"x": candidate.x, "y": candidate.y},
                "text_length": 0,
                "elapsed_ms": 0,
            }
        _cv2, _np, modules, _Image, _ImageGrab = _modules()
        win32api, win32con, _win32gui, _win32process, _win32ui = modules
        started = time.monotonic()
        block_input = lambda _blocked: True
        if not block_input(True):
            raise ExportAutomationError("INPUT_PROTECTION_FAILED", "Windows 未允许短暂保护键鼠，已取消动作")
        try:
            win32api.SetCursorPos((candidate.x, candidate.y))
            # Let Jianying receive the hover transition before the click.  The
            # QML surface does not reliably focus an input when it only receives
            # a posted WM_LBUTTON message, so use an injected mouse click.  The
            # low-level lease hook explicitly allows injected events through.
            time.sleep(0.12)
            # Jianying's home search icon both expands the field and gives the
            # QML input focus. Clicking the expanded field again collapses it
            # on Jianying 11.2, so preserve focus for this specific action.
            already_focused = action.input_kind == "replace_text" and candidate.locator == "home_search_input"
            # Jianying's parameter dialog is a QML child window.  Posted
            # WM_LBUTTON messages may update hover state without activating a
            # dropdown or folder control, so every state-changing Jianying
            # action uses the same tagged SendInput click as home search.
            real_click_required = action.input_kind in {"click", "choose_folder"} or (
                action.input_kind == "replace_text" and not already_focused
            )
            if real_click_required:
                self._inject_target_click(win32api, win32con, candidate.x, candidate.y)
            else:
                if action.input_kind != "replace_text":
                    self._post_target_click(candidate.x, candidate.y, win32con)
            if action.input_kind == "replace_text":
                self._replace_focused_text(win32api, win32con, action.input_text)
            elif action.input_kind == "choose_folder":
                self._choose_folder(Path(action.input_text))
        finally:
            # The lease owns the OS input block; release happens at handoff.
            pass
        return {
            "input": action.input_kind,
            "action_id": action.action_id,
            "point": {"x": candidate.x, "y": candidate.y},
            "text_length": len(action.input_text) if action.input_kind == "replace_text" else 0,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    @staticmethod
    def _inject_target_click(win32api: Any, win32con: Any, x: int, y: int) -> None:
        _cv2, _np, modules, _Image, _ImageGrab = _modules()
        _win32api, _win32con, win32gui, _win32process, _win32ui = modules
        try:
            win32api.SetCursorPos((int(x), int(y)))
            # SetCursorPos already places the pointer in screen coordinates.
            # Do not follow it with an absolute-coordinate MOVE: on a
            # multi-monitor/high-DPI desktop that second event is normalized
            # against the virtual desktop and can move the injected click away
            # from the verified target, leaving Jianying in hover state.
            time.sleep(0.12)
            WindowsInputLeaseAdapter.allow_automation_click(x, y)
            if LeaseGuardedWindowsActuator._send_input_click() != 2:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.08)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception as exc:
            raise ExportAutomationError("TARGET_WINDOW_CLICK_FAILED", f"无法向剪映注入点击：{exc}") from exc

    @staticmethod
    def _send_input_click() -> int:
        """Send a left click without remapping the positioned cursor."""
        if os.name != "nt":
            return 0
        class MouseInput(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
        class InputUnion(ctypes.Union):
            _fields_ = [("mi", MouseInput)]
        class Input(ctypes.Structure):
            _anonymous_ = ("union",)
            _fields_ = [("type", wintypes.DWORD), ("union", InputUnion)]
        inputs = (Input * 2)()
        inputs[0].mi.dwFlags = 0x0002
        inputs[0].mi.dwExtraInfo = _V1_AUTOMATION_INPUT_MARKER
        inputs[1].mi.dwFlags = 0x0004
        inputs[1].mi.dwExtraInfo = _V1_AUTOMATION_INPUT_MARKER
        return int(ctypes.windll.user32.SendInput(2, inputs, ctypes.sizeof(Input)))

    @staticmethod
    def _post_target_click(x: int, y: int, win32con: Any) -> None:
        _cv2, _np, modules, _Image, _ImageGrab = _modules()
        _win32api, _win32con, win32gui, _win32process, _win32ui = modules
        target = int(win32gui.WindowFromPoint((x, y)) or 0)
        if not target:
            raise ExportAutomationError("TARGET_WINDOW_MISSING", "点击坐标没有命中任何 Windows 窗口")
        client_x, client_y = win32gui.ScreenToClient(target, (x, y))
        if client_x < 0 or client_y < 0:
            raise ExportAutomationError("TARGET_CLIENT_POINT_INVALID", "点击坐标不在目标窗口客户区")
        lparam = (int(client_y) & 0xFFFF) << 16 | (int(client_x) & 0xFFFF)
        try:
            win32gui.PostMessage(target, win32con.WM_MOUSEMOVE, 0, lparam)
            win32gui.PostMessage(target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            time.sleep(0.08)
            win32gui.PostMessage(target, win32con.WM_LBUTTONUP, 0, lparam)
        except Exception as exc:
            raise ExportAutomationError("TARGET_WINDOW_CLICK_FAILED", f"无法向剪映目标窗口投递点击：{exc}") from exc

    @staticmethod
    def _choose_folder(target: Path, timeout_seconds: float = 6) -> None:
        target = target.resolve()
        if not target.is_dir():
            raise ExportAutomationError("OUTPUT_DIRECTORY_MISSING", "目标导出目录不存在")
        try:
            import uiautomation as auto
        except ImportError as exc:
            raise ExportAutomationError("FOLDER_PICKER_UNAVAILABLE", "缺少 Windows 文件夹选择自动化依赖") from exc
        deadline = time.monotonic() + timeout_seconds
        dialog = None
        while time.monotonic() < deadline:
            for control, _depth in auto.WalkControl(auto.GetRootControl(), maxDepth=3):
                if control.ControlTypeName == "WindowControl" and str(control.Name or "") == "请选择导出路径":
                    dialog = control
                    break
            if dialog is not None:
                break
            time.sleep(0.15)
        if dialog is None:
            raise ExportAutomationError("FOLDER_PICKER_NOT_FOUND", "剪映未打开 Windows 原生选择文件夹窗口")
        field = dialog.EditControl(AutomationId="1152")
        confirm = dialog.ButtonControl(AutomationId="1")
        if not field.Exists(1) or not confirm.Exists(1):
            raise ExportAutomationError("FOLDER_PICKER_CONTROLS_MISSING", "选择文件夹窗口缺少路径或确认控件")
        try:
            field.GetValuePattern().SetValue(str(target))
            actual = str(field.GetValuePattern().Value or "").strip()
        except Exception as exc:
            raise ExportAutomationError("FOLDER_PICKER_WRITE_FAILED", "无法写入 Windows 选择文件夹窗口") from exc
        try:
            verified = Path(actual).resolve() == target
        except OSError:
            verified = False
        if not verified:
            raise ExportAutomationError("FOLDER_PICKER_VERIFY_FAILED", "Windows 选择文件夹窗口未确认目标目录")
        confirm.Click(simulateMove=False)

    @staticmethod
    def _replace_focused_text(win32api: Any, win32con: Any, value: str) -> None:
        # Jianying's QML search field is known to accept the same Unicode
        # SendInput sequence used by the original fixed exporter.  A clipboard
        # write succeeding only proves that Windows accepted the clipboard
        # operation; it does not prove that QML received focus or a paste.
        # Therefore use the proven direct Unicode path first and keep paste as
        # a compatibility fallback for stripped-down/older Jianying builds.
        try:
            _press_key(win32api, win32con, ord("A"), control=True)
            _press_key(win32api, win32con, win32con.VK_BACK)
            for character in value:
                _send_unicode_character(character)
                time.sleep(0.015)
            return
        except Exception:
            pass

        # Clipboard paste remains useful on machines where SendInput Unicode
        # packets are filtered. Restore the user's clipboard shortly after the
        # paste so the automation does not permanently replace it.
        import win32clipboard

        previous_text: str | None = None
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previous_text = str(win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT))
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(value, win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        _press_key(win32api, win32con, ord("A"), control=True)
        _press_key(win32api, win32con, ord("V"), control=True)
        if previous_text is not None:
            threading.Timer(1.5, _restore_clipboard_text, args=(previous_text, win32con.CF_UNICODETEXT)).start()


def _press_key(win32api: Any, win32con: Any, key: int, *, control: bool = False) -> None:
    if control:
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(key, 0, 0, 0)
    win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
    if control:
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def _restore_clipboard_text(value: str, format_id: int) -> None:
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(value, format_id)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass


def _send_unicode_character(character: str) -> None:
    """Use SendInput Unicode packets so Chinese draft names and paths survive."""
    if len(character) != 1:
        raise ValueError("Unicode input expects one character")

    class KeybdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class MouseInput(ctypes.Structure):
        # INPUT is sized by its largest union member.  Leaving this out makes
        # the 64-bit keyboard packet too small for SendInput.
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class InputUnion(ctypes.Union):
        _fields_ = [("mi", MouseInput), ("ki", KeybdInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", InputUnion)]

    keyeventf_unicode = 0x0004
    keyeventf_keyup = 0x0002
    codepoint = ord(character)
    inputs = (Input * 2)(
        Input(1, InputUnion(ki=KeybdInput(0, codepoint, keyeventf_unicode, 0, None))),
        Input(1, InputUnion(ki=KeybdInput(0, codepoint, keyeventf_unicode | keyeventf_keyup, 0, None))),
    )
    sent = ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(Input))
    if sent != 2:
        raise JianyingAdapterError("Windows 未能写入剪映文本字段")


class WindowsInputLeaseAdapter:
    """Own the Windows desktop for one bounded foreground export sequence.

    Input is blocked for the lease lifetime; a watchdog and double-Esc listener
    provide emergency release paths if the worker stops responding.
    """

    _active_fallback_blocker: _LowLevelInputBlocker | None = None

    def __init__(self) -> None:
        self._lease_id: str | None = None
        self._input_blocker: _LowLevelInputBlocker | None = None
        self._pause_requested = threading.Event()
        self._stop_listener = threading.Event()
        self._listener: threading.Thread | None = None
        self._watchdog: threading.Thread | None = None
        self._lock = threading.Lock()

    def acquire(self, lease_id: str, maximum_seconds: float | None = None) -> None:
        with self._lock:
            if self._lease_id is not None:
                raise JianyingAdapterError("已有活动的 V1 键鼠接管")
            self._lease_id = lease_id
            self._pause_requested.clear()
            self._stop_listener = threading.Event()
            try:
                self._set_os_input_block(True)
            except JianyingAdapterError as block_error:
                blocker = _LowLevelInputBlocker()
                try:
                    blocker.start()
                except Exception as hook_error:
                    self._lease_id = None
                    raise JianyingAdapterError(
                        f"Windows 无法接管键鼠：BlockInput 不可用（{block_error}）；低级键鼠钩子也不可用（{hook_error}）"
                    ) from hook_error
                self._input_blocker = blocker
                WindowsInputLeaseAdapter._active_fallback_blocker = blocker
            self._listener = threading.Thread(
                target=self._watch_double_escape,
                args=(self._stop_listener,),
                name="v1-double-escape",
                daemon=True,
            )
            self._listener.start()
            if maximum_seconds and maximum_seconds > 0:
                self._watchdog = threading.Thread(
                    target=self._watch_lease_timeout,
                    args=(self._stop_listener, float(maximum_seconds)),
                    name="v1-input-watchdog",
                    daemon=True,
                )
                self._watchdog.start()

    def release(self, lease_id: str) -> None:
        with self._lock:
            if self._lease_id is not None and self._lease_id != lease_id:
                raise JianyingAdapterError("键鼠接管所有者不匹配")
            self._lease_id = None
            self._stop_listener.set()
            if self._input_blocker is not None:
                self._input_blocker.stop()
                if WindowsInputLeaseAdapter._active_fallback_blocker is self._input_blocker:
                    WindowsInputLeaseAdapter._active_fallback_blocker = None
                self._input_blocker = None
            self._set_os_input_block(False)

    def is_active(self, lease_id: str | None = None) -> bool:
        return self._lease_id is not None and (lease_id is None or self._lease_id == lease_id)

    def pause_requested(self, lease_id: str | None = None) -> bool:
        return self.is_active(lease_id) and self._pause_requested.is_set()

    def release_all(self) -> None:
        with self._lock:
            self._lease_id = None
            self._stop_listener.set()
            if self._input_blocker is not None:
                self._input_blocker.stop()
                if WindowsInputLeaseAdapter._active_fallback_blocker is self._input_blocker:
                    WindowsInputLeaseAdapter._active_fallback_blocker = None
                self._input_blocker = None
            self._set_os_input_block(False)

    @classmethod
    def allow_automation_click(cls, x: int, y: int) -> None:
        blocker = cls._active_fallback_blocker
        if blocker is not None:
            blocker.allow_click_at(x, y)

    @staticmethod
    def probe_capability() -> dict[str, object]:
        """Check OS input blocking separately from calibration and page reads.

        The probe only holds the OS flag for the duration of two Win32 calls.
        It gives the settings UI a concrete reason to block a real export
        before a foreground click is attempted.
        """
        if os.name != "nt":
            return {"available": False, "code": "UNSUPPORTED_PLATFORM", "detail": "键鼠接管只支持 Windows 桌面会话"}
        try:
            ctypes.set_last_error(0)
            acquired = bool(ctypes.windll.user32.BlockInput(True))
            error = ctypes.get_last_error()
            if acquired:
                ctypes.windll.user32.BlockInput(False)
                return {"available": True, "code": "OK", "method": "block_input", "detail": "Windows 允许 BlockInput 独占键鼠"}
            detail = ctypes.FormatError(error).strip() if error else "Windows 拒绝接管键鼠"
            try:
                _LowLevelInputBlocker.probe()
            except Exception as hook_error:
                return {
                    "available": False, "code": "INPUT_PROTECTION_UNAVAILABLE", "win32_error": error,
                    "detail": f"{detail}；低级键鼠钩子不可用：{hook_error}",
                }
            return {
                "available": True, "code": "HOOK_FALLBACK", "method": "low_level_hook", "win32_error": error,
                "detail": "Windows 不允许 BlockInput，已切换并验证低级键鼠钩子接管可用",
            }
        except Exception as exc:  # pragma: no cover - Windows API behavior
            try:
                ctypes.windll.user32.BlockInput(False)
            except Exception:
                pass
            return {"available": False, "code": "BLOCK_INPUT_PROBE_FAILED", "detail": f"无法检查 Windows 键鼠接管：{exc}"}

    @staticmethod
    def _set_os_input_block(blocked: bool) -> None:
        if os.name != "nt":
            return
        try:
            result = ctypes.windll.user32.BlockInput(bool(blocked))
        except Exception as exc:
            if blocked:
                raise JianyingAdapterError(f"Windows 无法接管键鼠：{exc}") from exc
            return
        if blocked and not result:
            error = ctypes.get_last_error()
            detail = ctypes.FormatError(error).strip() if error else "Windows 拒绝接管键鼠"
            raise JianyingAdapterError(f"Windows 拒绝接管键鼠：{detail}")

    def _watch_lease_timeout(self, stop_listener: threading.Event, maximum_seconds: float) -> None:
        if stop_listener.wait(maximum_seconds):
            return
        self._pause_requested.set()
        with self._lock:
            if self._stop_listener is stop_listener:
                stop_listener.set()
                self._set_os_input_block(False)

    def _watch_double_escape(self, stop_listener: threading.Event) -> None:
        """Poll only while a V1 lease exists; no global keyboard hook is retained."""
        if os.name != "nt":
            return
        detector = _DoubleEscapeDetector()
        while not stop_listener.wait(0.02):
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
            except Exception:
                return
            if detector.observe(down, time.monotonic()):
                self._pause_requested.set()
                return


class _LowLevelInputBlocker:
    """Fallback input owner for Windows sessions that reject ``BlockInput``.

    A low-level hook consumes physical keyboard and mouse messages in the
    current interactive desktop.  Events injected by the executor are allowed
    through.  Escape remains available so the adapter's existing double-Esc
    listener can always request an emergency release.
    """

    _WH_KEYBOARD_LL = 13
    _WH_MOUSE_LL = 14
    _HC_ACTION = 0
    _WM_KEYDOWN = 0x0100
    _WM_KEYUP = 0x0101
    _WM_SYSKEYDOWN = 0x0104
    _WM_SYSKEYUP = 0x0105
    _WM_QUIT = 0x0012
    _WM_LBUTTONDOWN = 0x0201
    _WM_LBUTTONUP = 0x0202
    _VK_ESCAPE = 0x1B
    _LLKHF_INJECTED = 0x10
    _LLMHF_INJECTED = 0x01

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._error: Exception | None = None
        self._keyboard_hook = None
        self._mouse_hook = None
        self._keyboard_proc = None
        self._mouse_proc = None
        self._allowed_click: tuple[int, int, float] | None = None

    def allow_click_at(self, x: int, y: int, seconds: float = 0.5) -> None:
        self._allowed_click = (int(x), int(y), time.monotonic() + max(0.1, float(seconds)))

    @classmethod
    def probe(cls) -> None:
        blocker = cls()
        blocker.start()
        blocker.stop()

    def start(self) -> None:
        if os.name != "nt":
            raise JianyingAdapterError("低级键鼠钩子只支持 Windows")
        self._thread = threading.Thread(target=self._run, name="v1-input-hook", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            self.stop()
            raise JianyingAdapterError("低级键鼠钩子启动超时")
        if self._error is not None:
            raise JianyingAdapterError(str(self._error)) from self._error

    def stop(self) -> None:
        self._stop.set()
        if os.name == "nt" and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, self._WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self) -> None:  # pragma: no cover - Windows hook callback behavior
        try:
            self._install_and_pump()
        except Exception as exc:
            self._error = exc
            self._ready.set()
        finally:
            self._uninstall()

    def _install_and_pump(self) -> None:  # pragma: no cover - Windows hook callback behavior
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class Keyboard(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

        class Mouse(ctypes.Structure):
            _fields_ = [("pt", Point), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

        class Message(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", Point), ("lPrivate", wintypes.DWORD)]

        # A low-level hook receives a 64-bit pointer in lParam on 64-bit
        # Windows. Leaving CallNextHookEx without argtypes makes ctypes coerce
        # that pointer to a 32-bit int and drops allowed injected events.
        hook_proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._thread_id = int(kernel32.GetCurrentThreadId())

        def keyboard(code, message, data):
            if code != self._HC_ACTION or self._stop.is_set():
                return user32.CallNextHookEx(None, code, message, data)
            event = ctypes.cast(data, ctypes.POINTER(Keyboard)).contents
            injected = bool(int(event.flags) & self._LLKHF_INJECTED)
            is_escape = int(event.vkCode) == self._VK_ESCAPE
            if injected or is_escape:
                return user32.CallNextHookEx(None, code, message, data)
            if int(message) in {self._WM_KEYDOWN, self._WM_KEYUP, self._WM_SYSKEYDOWN, self._WM_SYSKEYUP}:
                return 1
            return user32.CallNextHookEx(None, code, message, data)

        def mouse(code, message, data):
            if code != self._HC_ACTION or self._stop.is_set():
                return user32.CallNextHookEx(None, code, message, data)
            event = ctypes.cast(data, ctypes.POINTER(Mouse)).contents
            allowed_click = self._allowed_click
            expected_click = (
                allowed_click is not None
                and time.monotonic() <= allowed_click[2]
                and int(message) in {self._WM_LBUTTONDOWN, self._WM_LBUTTONUP}
                and abs(int(event.pt.x) - allowed_click[0]) <= 3
                and abs(int(event.pt.y) - allowed_click[1]) <= 3
            )
            if bool(int(event.flags) & self._LLMHF_INJECTED) or int(event.dwExtraInfo or 0) == _V1_AUTOMATION_INPUT_MARKER or expected_click:
                return user32.CallNextHookEx(None, code, message, data)
            return 1

        self._keyboard_proc = hook_proc(keyboard)
        self._mouse_proc = hook_proc(mouse)
        module = kernel32.GetModuleHandleW(None)
        self._keyboard_hook = user32.SetWindowsHookExW(self._WH_KEYBOARD_LL, self._keyboard_proc, module, 0)
        self._mouse_hook = user32.SetWindowsHookExW(self._WH_MOUSE_LL, self._mouse_proc, module, 0)
        if not self._keyboard_hook or not self._mouse_hook:
            error = ctypes.get_last_error()
            raise JianyingAdapterError(ctypes.FormatError(error).strip() if error else "Windows 拒绝安装低级键鼠钩子")
        self._ready.set()
        message = Message()
        while not self._stop.is_set():
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result <= 0:
                break
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _uninstall(self) -> None:  # pragma: no cover - Windows hook callback behavior
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            if self._keyboard_hook:
                user32.UnhookWindowsHookEx(self._keyboard_hook)
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
        finally:
            self._keyboard_hook = None
            self._mouse_hook = None


class _DoubleEscapeDetector:
    """Small state machine kept separate so the timing rule is unit-testable."""

    def __init__(self, maximum_gap_seconds: float = 0.75) -> None:
        self.maximum_gap_seconds = maximum_gap_seconds
        self._was_down = False
        self._last_press_at: float | None = None

    def observe(self, down: bool, now: float) -> bool:
        detected = False
        if down and not self._was_down:
            detected = self._last_press_at is not None and now - self._last_press_at <= self.maximum_gap_seconds
            self._last_press_at = now
        self._was_down = down
        return detected
