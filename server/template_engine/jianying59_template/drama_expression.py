"""Local facial-expression measurement for the template photo wall.

Why this exists
---------------
The 2026-09-18 hand-rolled attempt at "are the eyes open?" used the ratio of
vertical to horizontal edge energy around the eye.  Checked against real frames,
that metric actually measured **occlusion and glare** (a hand over the face, a
phone, glasses catching the light) and not eyelid state, so it was abandoned.

MediaPipe's Face Landmarker provides real blendshape coefficients, including
``eyeBlinkLeft`` / ``eyeBlinkRight`` and ``jawOpen`` / ``mouthSmile*``, which is
exactly the measurement that was missing.  Measured on real material: ~15 ms per
frame and a 3.6 MB model.

Two deliberate engineering choices
----------------------------------
1. **matplotlib is stubbed out.**  ``mediapipe.tasks.python.vision`` imports
   ``drawing_styles`` → ``drawing_utils`` → ``matplotlib.pyplot`` at module load,
   purely to draw landmark overlays we never use.  Installing matplotlib just to
   satisfy that import would add a large dependency to the Portable package, so a
   minimal stand-in module is registered *before* mediapipe is imported.  This is
   verified to allow full landmark + blendshape inference without matplotlib.
2. **Never a hard failure.**  Missing model or missing mediapipe → returns "no
   expression data" and callers fall back to the previous behaviour.  A photo
   wall must not fail a production task because a measurement is unavailable.

License: MediaPipe is Apache 2.0; the bundled model is from Google's model CDN.
"""

from __future__ import annotations

import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_RESOURCE_NAME = "face_landmarker.task"
MAX_FACES = 3

# 实测：睁眼时 eyeBlink 通常 <0.2，闭眼/眯眼明显升高；jawOpen >0.4 基本是在喊。
EYES_CLOSED = 0.5
MOUTH_SHOUTING = 0.45
SMILE_THRESHOLD = 0.35

_LOCK = threading.Lock()
_LANDMARKER: Any | None = None
_LANDMARKER_FAILED = False
_SHUTTING_DOWN = False


def _install_shutdown_guard() -> None:
    """Keep MediaPipe's teardown quiet at interpreter exit.

    ``FaceLandmarker.__del__`` calls into the native dispatcher, which is already
    torn down by the time Python finalises modules; the result is a noisy
    "Exception ignored in ... TypeError: 'NoneType' object is not callable" that
    gets relayed into task logs.  We hold the instance for the process lifetime
    and close it ourselves, ignoring failures during shutdown.
    """
    global _SHUTTING_DOWN

    import atexit

    def _close() -> None:
        global _SHUTTING_DOWN
        _SHUTTING_DOWN = True
        landmarker = _LANDMARKER
        if landmarker is None:
            return
        try:
            landmarker.close()
        except Exception:
            pass

    atexit.register(_close)


def model_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / MODEL_RESOURCE_NAME


def _install_matplotlib_stub() -> None:
    """Register a stand-in ``matplotlib`` so mediapipe's unused drawing helper imports.

    The stub is only put in place when the real package is absent, and it is
    never used for anything: mediapipe imports ``matplotlib.pyplot`` at module
    scope but our code path (landmarks + blendshapes) never draws.
    """
    if "matplotlib" in sys.modules:
        return
    try:
        import matplotlib  # noqa: F401
        return
    except ImportError:
        pass
    package = types.ModuleType("matplotlib")
    package.__path__ = []  # mark it as a package so submodule import works
    pyplot = types.ModuleType("matplotlib.pyplot")
    package.pyplot = pyplot
    sys.modules["matplotlib"] = package
    sys.modules["matplotlib.pyplot"] = pyplot


def _landmarker() -> Any | None:
    global _LANDMARKER, _LANDMARKER_FAILED
    if _LANDMARKER is not None or _LANDMARKER_FAILED:
        return _LANDMARKER
    with _LOCK:
        if _LANDMARKER is not None or _LANDMARKER_FAILED:
            return _LANDMARKER
        path = model_path()
        if not path.is_file():
            _LANDMARKER_FAILED = True
            return None
        try:
            _install_matplotlib_stub()
            from mediapipe.tasks import python as mediapipe_python
            from mediapipe.tasks.python import vision
            options = vision.FaceLandmarkerOptions(
                base_options=mediapipe_python.BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=MAX_FACES,
                output_face_blendshapes=True,
                min_face_detection_confidence=0.5,
            )
            _LANDMARKER = vision.FaceLandmarker.create_from_options(options)
            # MediaPipe's __del__ calls into the native dispatcher, which Python has
            # already torn down by the time the object is collected at exit; the
            # result is a noisy "Exception ignored in ... TypeError" that gets
            # relayed into task logs.  We close it ourselves via the atexit guard,
            # so silence the destructor.
            try:
                type(_LANDMARKER).__del__ = lambda self: None  # type: ignore[method-assign]
            except (AttributeError, TypeError):
                pass
            _install_shutdown_guard()
        except Exception:
            _LANDMARKER_FAILED = True
            return None
    return _LANDMARKER


def available() -> bool:
    return _landmarker() is not None


@dataclass(frozen=True)
class Expression:
    """Expression measurement for one face, already reduced to what we judge on."""

    eyes_closed: float
    mouth_open: float
    smile: float
    face_width_ratio: float  # 人脸宽度占画面宽度的比例，用于和 YuNet 的结果交叉校验

    @property
    def eyes_shut(self) -> bool:
        return self.eyes_closed >= EYES_CLOSED

    @property
    def shouting(self) -> bool:
        return self.mouth_open >= MOUTH_SHOUTING

    @property
    def smiling(self) -> bool:
        return self.smile >= SMILE_THRESHOLD


def measure(image: Any) -> Expression | None:
    """Return the expression of the **largest** face in a BGR image, or None.

    ``image`` is an OpenCV BGR array (as produced by ``cv2.imdecode``).
    """
    landmarker = _landmarker()
    if landmarker is None or _SHUTTING_DOWN or image is None or getattr(image, "size", 0) == 0:
        return None
    import cv2

    try:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    except Exception:
        return None
    try:
        import mediapipe as mp
        mediapipe_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        with _LOCK:
            result = landmarker.detect(mediapipe_image)
    except Exception:
        return None
    if not result.face_landmarks:
        return None

    height, width = image.shape[:2]
    best_index = 0
    best_width = -1.0
    for index, landmarks in enumerate(result.face_landmarks):
        xs = [point.x for point in landmarks]
        span = max(xs) - min(xs)
        if span > best_width:
            best_width, best_index = span, index

    blendshapes: dict[str, float] = {}
    if result.face_blendshapes and best_index < len(result.face_blendshapes):
        blendshapes = {
            item.category_name: float(item.score) for item in result.face_blendshapes[best_index]
        }
    eyes_closed = (blendshapes.get("eyeBlinkLeft", 0.0) + blendshapes.get("eyeBlinkRight", 0.0)) / 2.0
    smile = (blendshapes.get("mouthSmileLeft", 0.0) + blendshapes.get("mouthSmileRight", 0.0)) / 2.0
    return Expression(
        eyes_closed=round(eyes_closed, 4),
        mouth_open=round(blendshapes.get("jawOpen", 0.0), 4),
        smile=round(smile, 4),
        face_width_ratio=round(best_width, 5) if width else 0.0,
    )
