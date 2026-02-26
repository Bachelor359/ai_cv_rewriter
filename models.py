from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class SlotLocation(str, Enum):
    BODY = "body"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    TEXTBOX = "textbox"


class CVSlot(BaseModel):
    """One addressable paragraph inside the DOCX."""
    slot_id: int
    text: str
    location: SlotLocation
    style_name: str

    # Navigation indices — meaning depends on location:
    #   BODY:    [para_idx]
    #   TABLE:   [table_idx, row_idx, col_idx, para_idx]
    #   HEADER:  [section_idx, para_idx]
    #   FOOTER:  [section_idx, para_idx]
    #   TEXTBOX: [textbox_idx, para_idx]
    indices: list[int]

    # If this slot is a visual line-wrap continuation of a longer paragraph,
    # this points to the primary slot's slot_id.  None means this IS a primary.
    merged_into: Optional[int] = None


class CVStructure(BaseModel):
    """Full extracted structure of the original CV."""
    slots: list[CVSlot]

    def slot_by_id(self, slot_id: int) -> Optional[CVSlot]:
        for s in self.slots:
            if s.slot_id == slot_id:
                return s
        return None

    def non_empty_slots(self) -> list[CVSlot]:
        return [s for s in self.slots if s.text.strip()]

    def primary_slots(self) -> list[CVSlot]:
        """Slots that are not continuations of another slot."""
        return [s for s in self.slots if s.merged_into is None]

    def to_prompt_lines(self) -> str:
        """
        Compact representation for the LLM: [id] (style) text

        Continuation slots are merged into their primary slot's text so the
        LLM sees a single complete sentence under one slot_id.  When the LLM
        rewrites slot N, Stage 3 will write that text to slot N's paragraph
        and blank out all continuation paragraphs that follow it.
        """
        # Build merged text per primary slot
        merged: dict[int, str] = {}
        for s in self.slots:
            primary_id = s.merged_into if s.merged_into is not None else s.slot_id
            if primary_id not in merged:
                merged[primary_id] = ""
            merged[primary_id] = (merged[primary_id] + " " + s.text).strip()

        lines = []
        for s in self.slots:
            if s.merged_into is not None:
                continue  # skip continuations — already folded into primary
            full_text = merged.get(s.slot_id, s.text).strip()
            if full_text:
                lines.append(f"[{s.slot_id}] ({s.style_name}) {full_text}")
        return "\n".join(lines)


class RewriteResult(BaseModel):
    """LLM rewrite output for one job description."""
    company: str
    timestamp: str
    # slot_id as str (JSON keys are always strings) -> rewritten text
    slots: dict[str, str]
    raw_json_path: str
