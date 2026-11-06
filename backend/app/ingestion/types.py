from dataclasses import dataclass, field
from typing import Literal, Optional


BlockKind = Literal["paragraph", "heading", "table", "list", "ocr"]


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ContentBlock:
    text: str
    kind: BlockKind = "paragraph"
    page_number: int = 1
    confidence: Optional[float] = None
    bbox: Optional[BBox] = None
    reading_order: int = 0


@dataclass
class ExtractedPage:
    page_number: int
    blocks: list[ContentBlock] = field(default_factory=list)
    source: str = "native"  # native | ocr | mixed | text

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text.strip())


@dataclass
class ExtractedDocument:
    pages: list[ExtractedPage] = field(default_factory=list)
    filename: str = ""
    file_type: str = ""

    @property
    def full_text(self) -> str:
        parts: list[str] = []
        for page in self.pages:
            page_text = page.text.strip()
            if page_text:
                parts.append(page_text)
        return "\n\n".join(parts)


@dataclass
class TextChunk:
    content: str
    page_number: Optional[int]
    chunk_index: int
    token_count: int
