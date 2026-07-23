"""Pluggable subject/face detection interface.

There is NO real face detector in this repository, and none is silently
downloaded — subject protection today is deterministic template geometry
(the protected_subject_region that compositor content must not enter).
This interface exists so a future local detector can supply *observed*
subject boxes; when boxes are provided, layout QA additionally fails any
text/QR/logo that overlaps a detected subject. Tests exercise the
interface with deterministic fake detections.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SubjectBox:
    x: int
    y: int
    width: int
    height: int
    kind: str = "face"


class SubjectDetector(Protocol):
    def detect(self, png_bytes: bytes) -> list[SubjectBox]:
        ...


class NullSubjectDetector:
    """Default: no observed detections; template geometry alone protects
    the subject region."""

    def detect(self, png_bytes: bytes) -> list[SubjectBox]:
        return []
