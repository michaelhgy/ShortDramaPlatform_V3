"""Local face-identity comparison, so one actor cannot fill the whole photo wall.

Why this exists
---------------
Measured on the real 2026-09-18 output: 3 of the 10 wall photos were the *same*
actor.  "At most 3 photos per episode" prevents ten stills from one scene, but it
cannot prevent the same face appearing across episodes.

How it works (and why not the InsightFace package)
--------------------------------------------------
The ArcFace ``w600k_mbf`` model is used directly through the project's existing
ONNX Runtime.  Measured against the full ``insightface`` package on the same
material, the similarity scores were equivalent (same actor 0.69–1.00, different
actors −0.19–0.36), while adding **no** new runtime dependency — the package
would also have pulled in ``onnx``, ``scikit-image``, ``scipy`` and
``matplotlib``.  Only the alignment step is ours: the two eye points from YuNet's
five landmarks are rotated and scaled onto ArcFace's canonical template.

Decision threshold: **0.5** (clear separation was measured between 0.36 and 0.69).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MODEL_RESOURCE_NAME = "arcface_w600k_mbf.onnx"
SAME_PERSON_THRESHOLD = 0.5
# ArcFace 标准 112x112 模板上的两眼坐标（左眼、右眼）
ARCFACE_TEMPLATE = ((38.2946, 51.6963), (73.5318, 51.5014))

_LOCK = threading.Lock()
_SESSION: Any | None = None
_SESSION_FAILED = False


def model_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / MODEL_RESOURCE_NAME


def _session() -> Any | None:
    global _SESSION, _SESSION_FAILED
    if _SESSION is not None or _SESSION_FAILED:
        return _SESSION
    with _LOCK:
        if _SESSION is not None or _SESSION_FAILED:
            return _SESSION
        path = model_path()
        if not path.is_file():
            _SESSION_FAILED = True
            return None
        try:
            import onnxruntime

            _SESSION = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        except Exception:
            _SESSION_FAILED = True
            return None
    return _SESSION


def available() -> bool:
    return _session() is not None


@dataclass(frozen=True)
class FaceIdentity:
    """A unit-normalised face embedding; cosine similarity via dot product."""

    vector: Any

    def similarity(self, other: "FaceIdentity") -> float:
        import numpy

        return float(numpy.dot(self.vector, other.vector))

    def is_same_person(self, other: "FaceIdentity", *, threshold: float = SAME_PERSON_THRESHOLD) -> bool:
        return self.similarity(other) >= threshold


def identity_of(image: Any, face: Any) -> FaceIdentity | None:
    """Return the identity embedding for ``face`` (a :class:`drama_face.FaceBox`).

    ``image`` is an OpenCV BGR array.  Returns None when the model is missing or
    the alignment cannot be computed — callers then simply skip identity checks.
    """
    session = _session()
    if session is None or image is None or face is None:
        return None
    import cv2
    import numpy

    # YuNet landmark order: rightEye, leftEye, nose, rightMouth, leftMouth.
    # ``face.right_eye()/left_eye()`` are computed from the stored landmarks.
    try:
        right_eye = face.right_eye
        left_eye = face.left_eye
    except AttributeError:
        return None
    if right_eye is None or left_eye is None:
        return None

    source = numpy.array([right_eye, left_eye], dtype=numpy.float32)
    target = numpy.array(ARCFACE_TEMPLATE, dtype=numpy.float32)
    try:
        matrix, _inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.LMEDS)
        if matrix is None:
            return None
        aligned = cv2.warpAffine(image, matrix, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 128.0, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        input_name = session.get_inputs()[0].name
        with _LOCK:
            embedding = session.run(None, {input_name: blob})[0].flatten()
    except Exception:
        return None
    norm = float(numpy.linalg.norm(embedding))
    if norm <= 0:
        return None
    return FaceIdentity(vector=embedding / norm)


def deduplicate(
    items: Iterable[tuple[Any, FaceIdentity | None]], *, max_per_person: int = 2,
) -> list[Any]:
    """Keep at most ``max_per_person`` entries per distinct person.

    ``items`` is an ordered sequence of ``(payload, identity)`` pairs (best first).
    Entries with ``identity is None`` (no model, or no face) are always kept: an
    unavailable measurement must never silently drop a candidate.
    """
    kept: list[Any] = []
    accepted: list[FaceIdentity] = []
    per_person: list[int] = []
    for payload, identity in items:
        if identity is None:
            kept.append(payload)
            continue
        match = next(
            (index for index, known in enumerate(accepted) if identity.is_same_person(known)),
            None,
        )
        if match is None:
            accepted.append(identity)
            per_person.append(1)
            kept.append(payload)
        elif per_person[match] < max_per_person:
            per_person[match] += 1
            kept.append(payload)
    return kept
