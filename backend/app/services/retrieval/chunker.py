"""Split documents into passages that keep their source locator.

Chunking happens *inside* a section, never across sections, so every passage
still knows whether it came from "Page 3", "Slide 7" or "Sheet: Results". That
is what lets retrieval keep the citation feature working: a retrieved passage
carries the same locator the model is asked to cite.

Paragraphs are packed into chunks rather than cut at a fixed word count, so
Markdown tables and bullet lists stay in one piece.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.document import DocumentContent


@dataclass
class Chunk:
    document_id: str
    document_index: int  # 1-based position in the current selection -> the "S1" in [S1: Page 3]
    document_name: str
    section_id: str
    locator: str
    text: str
    order: int  # position of the chunk inside its document
    tokens: list[str] = field(default_factory=list)  # filled by the index

    @property
    def key(self) -> tuple[str, int]:
        return (self.document_id, self.order)


def _paragraphs(markdown: str) -> list[str]:
    """Blank-line separated blocks; consecutive table/list lines stay together."""
    blocks: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def chunk_document(doc: DocumentContent, index: int, target_words: int, overlap_paragraphs: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    order = 0
    for section in doc.sections:
        blocks = _paragraphs(section.markdown)
        if not blocks:
            continue
        buffer: list[str] = []
        words = 0
        for block in blocks:
            block_words = len(block.split())
            # Flush first when this block would overflow the target. A block
            # larger than the target simply becomes its own chunk.
            if buffer and words + block_words > target_words:
                chunks.append(_make(doc, index, section, "\n\n".join(buffer), order))
                order += 1
                overlap = buffer[-overlap_paragraphs:] if overlap_paragraphs else []
                # Never carry an overlap that is already at/over the target, or
                # the next chunk would start full and could never make progress.
                if sum(len(b.split()) for b in overlap) >= target_words:
                    overlap = []
                buffer = list(overlap)
                words = sum(len(b.split()) for b in buffer)
            buffer.append(block)
            words += block_words
        if buffer:
            chunks.append(_make(doc, index, section, "\n\n".join(buffer), order))
            order += 1
    return chunks


def _make(doc: DocumentContent, index: int, section, text: str, order: int) -> Chunk:
    return Chunk(
        document_id=doc.id,
        document_index=index,
        document_name=doc.display_name,
        section_id=section.section_id,
        locator=section.locator,
        text=text.strip(),
        order=order,
    )


def chunk_documents(documents: list[DocumentContent], target_words: int = 180, overlap_paragraphs: int = 1) -> list[Chunk]:
    out: list[Chunk] = []
    for i, doc in enumerate(documents, start=1):
        out.extend(chunk_document(doc, i, target_words, overlap_paragraphs))
    return out
