"""Published class guides rendered as knowledge base chunks (feature 043, sc-112 AC3).

One chunk per markdown section (a ``#``/``##``/``###`` heading and the text up to the next
one), with the class, spec, role, content type and section title in the text so a search for
"arms warrior rotation" finds it. A section longer than one chunk is split into parts at
paragraph breaks. Claim markers are stripped (they are for the viewer's evidence links). Only
a published guide is chunked; republishing replaces the guide's chunks (``kb/store.py``).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from .chunks import MAX_LABEL, MAX_TEXT, ChunkDraft
from .names import class_spec

MAX_PARTS = 5  # per section; the rest of a very long section is left out
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
_CONTENT = {"raid": "raid", "mplus": "Mythic+"}


@dataclass(frozen=True)
class GuideJob:
    """A published guide to (re)chunk: the columns the publish hook already holds."""

    guide_id: uuid.UUID
    class_name: str
    spec: str
    content_type: str
    markdown: str
    patch: str | None = None


def _sections(markdown: str) -> list[tuple[str, str]]:
    """(title, body) per heading; text before the first heading is an "Overview"."""
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in markdown.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            sections.append((heading.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(title, "\n".join(lines).strip()) for title, lines in sections if "\n".join(lines).strip()]


def _parts(body: str, room: int) -> list[str]:
    """``body`` in pieces of at most ``room`` characters, split at paragraph breaks."""
    room = max(room, 1)  # a part must always make progress
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", body):
        while len(paragraph) > room:  # one huge paragraph: split at the last space that fits
            if current:
                parts.append(current)
                current = ""
            cut = paragraph.rfind(" ", room // 2, room)
            cut = cut if cut > 0 else room
            parts.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        if current and len(current) + 2 + len(paragraph) > room:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts[:MAX_PARTS]


def chunk_guide(job: GuideJob) -> list[ChunkDraft]:
    # Imported here: the guide pipeline package imports the indexer, which imports this module.
    from ..services.guide_pipeline.render import strip_claim_markers

    cls, spec, role = class_spec(job.class_name, job.spec)
    cls, spec = cls or job.class_name, spec or job.spec
    content = _CONTENT.get(job.content_type, job.content_type)
    drafts: list[ChunkDraft] = []
    for index, (title, body) in enumerate(_sections(strip_claim_markers(job.markdown) or "")):
        head = f"{spec} {cls} ({role or 'unknown role'}) {content} guide, section {title[:MAX_LABEL]}"
        parts = _parts(body, max(MAX_TEXT - len(head) - 12, MAX_TEXT // 2))
        for number, part in enumerate(parts, start=1):
            suffix = f" ({number}/{len(parts)})" if len(parts) > 1 else ""
            drafts.append(
                ChunkDraft(
                    chunk_key=f"section:{index}:{number}",
                    label=f"{title}{suffix}",
                    text=f"{head}{suffix}:\n{part}",
                    class_name=cls,
                    spec=spec,
                    role=role,
                    content_type=job.content_type,
                    patch=job.patch,
                    section=title,
                )
            )
    return drafts
