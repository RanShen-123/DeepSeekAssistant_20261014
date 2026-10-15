"""明确区分识别证据、页面状态和候选控件，未知值用 None。"""
from dataclasses import dataclass, field, asdict


@dataclass
class TextLine:
    text: str
    score: float
    bbox: list[int]

    @property
    def center(self):
        x, y, w, h = self.bbox
        return [x+w//2, y+h//2]


@dataclass
class Control:
    id: str
    kind: str
    label: str | None
    bbox: list[int]
    center: list[int]
    confidence: float
    evidence: str
    selected: bool | None = None
    enabled: bool | None = None
    state: str | None = None
    question_number: int | None = None


@dataclass
class PageResult:
    image_size: list[int]
    question_type: str | None = None
    header_question_number: int | None = None
    header_evidence: dict | None = None
    sidebar_question_number: int | None = None
    current_question_number: int | None = None
    question_number_consistent: bool | None = None
    completed_count: int | None = None
    total_count: int | None = None
    progress_evidence: str | None = None
    question_text: str | None = None
    controls: list[Control] = field(default_factory=list)
    texts: list[TextLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return {"schema_version": 1, "coordinate_system": "image_pixels", **asdict(self)}
