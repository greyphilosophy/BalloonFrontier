from __future__ import annotations

import dataclasses
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


_MD_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL | re.MULTILINE)
_MD_HEADING2_RE = re.compile(r"^##\s+(.*)\s*$", re.MULTILINE)


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "step"


def _extract_front_matter(md: str) -> Dict[str, str]:
    m = _MD_FRONT_MATTER_RE.search(md)
    if not m:
        return {}
    raw = m.group(1)
    out: Dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        # Strip surrounding quotes if present.
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        out[k] = v
    return out


def _extract_checklist_items(md_body: str) -> List[str]:
    # Matches markdown checkboxes like: - [ ] item
    # or: - [x] item
    items: List[str] = []
    for m in re.finditer(r"^\s*-\s*\[[ xX\u2713\u2714]\]\s*(.+?)\s*$", md_body, flags=re.MULTILINE):
        items.append(m.group(1).strip())
    return items


def _extract_quick_hint(md_body: str) -> str:
    # Heuristic: first non-empty paragraph (up to 2 newlines).
    # This is used for UI so we don't show a full wall of text.
    lines = [ln.rstrip() for ln in md_body.splitlines()]
    # Skip empty / separator lines.
    buf: List[str] = []
    in_paragraph = False
    for ln in lines:
        stripped = ln.strip()
        if not stripped or stripped in {"---", "***"}:
            if in_paragraph:
                break
            continue
        in_paragraph = True
        buf.append(stripped)
        # Stop after some reasonable size to avoid huge hints.
        if sum(len(x) for x in buf) > 240:
            break
    paragraph = " ".join(buf).strip()
    return paragraph or ""


def _split_steps(md: str) -> List[Tuple[str, str]]:
    """Returns list of (heading, body_md) for each ## heading."""
    # Remove YAML front matter so headings indices align.
    fm_match = _MD_FRONT_MATTER_RE.search(md)
    if fm_match:
        md_wo_fm = md[fm_match.end() :]
    else:
        md_wo_fm = md

    # Find all headings and slice bodies accordingly.
    headings = []
    for m in _MD_HEADING2_RE.finditer(md_wo_fm):
        headings.append((m.start(), m.group(1).strip()))

    if not headings:
        return []

    steps: List[Tuple[str, str]] = []
    for i, (pos, heading) in enumerate(headings):
        next_pos = headings[i + 1][0] if i + 1 < len(headings) else len(md_wo_fm)
        body = md_wo_fm[pos:next_pos]
        # Strip the heading line itself.
        body_lines = body.splitlines()
        if body_lines:
            body = "\n".join(body_lines[1:]).strip()  # drop heading
        steps.append((heading, body))

    return steps


@dataclass(frozen=True)
class TutorialStep:
    step_index: int
    step_id: str
    heading: str
    instructions_md: str
    help_items: Tuple[str, ...] = ()
    quick_hint: str = ""

    @classmethod
    def from_heading(cls, *, step_index: int, heading: str, body_md: str) -> "TutorialStep":
        step_id = _slugify(heading)
        help_items = tuple(_extract_checklist_items(body_md))
        quick_hint = _extract_quick_hint(body_md)
        return cls(
            step_index=step_index,
            step_id=step_id,
            heading=heading,
            instructions_md=body_md.strip(),
            help_items=help_items,
            quick_hint=quick_hint,
        )

    def to_ui(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "step_id": self.step_id,
            "heading": self.heading,
            "instructions": self.instructions_md,
            "help_items": list(self.help_items),
            "quick_hint": self.quick_hint,
        }


@dataclass(frozen=True)
class TutorialDefinition:
    tutorial_id: str
    title: str
    section: str
    steps: Tuple[TutorialStep, ...]

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def to_ui(self) -> Dict[str, Any]:
        return {
            "tutorial_id": self.tutorial_id,
            "title": self.title,
            "section": self.section,
            "total_steps": self.total_steps,
            "steps": [s.to_ui() for s in self.steps],
        }


@dataclass(frozen=True)
class TutorialSession:
    tutorial_id: str
    current_step_id: Optional[str]
    completed_step_ids: Tuple[str, ...] = ()
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def _completed_set(self) -> Set[str]:
        return set(self.completed_step_ids)

    def progress(self, *, total_steps: int) -> Dict[str, Any]:
        done = len(self._completed_set())
        total = max(total_steps, 1)
        return {
            "completed_steps": done,
            "total_steps": total,
            "progress_ratio": min(1.0, done / total),
        }

    def is_step_completed(self, step_id: str) -> bool:
        return step_id in self._completed_set()

    def complete_step(self, step_id: str, *, next_step_id: Optional[str]) -> "TutorialSession":
        completed = set(self.completed_step_ids)
        completed.add(step_id)
        now = time.time()
        return dataclasses.replace(
            self,
            current_step_id=next_step_id,
            completed_step_ids=tuple(sorted(completed)),
            updated_at=now,
        )

    def to_ui(self, *, definition: TutorialDefinition) -> Dict[str, Any]:
        cur_idx = None
        if self.current_step_id is not None:
            for s in definition.steps:
                if s.step_id == self.current_step_id:
                    cur_idx = s.step_index
                    break

        prog = self.progress(total_steps=definition.total_steps)
        return {
            "tutorial_id": self.tutorial_id,
            "current_step_id": self.current_step_id,
            "current_step_index": cur_idx,
            "completed_step_ids": list(self.completed_step_ids),
            "progress": prog,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "skills": {
                # For now we treat the front-matter "section" as the primary skill track.
                # If later we want multi-skill granularity, we can extend this.
                "primary_skill": {
                    "skill_id": _slugify(definition.section),
                    "mastery_ratio": prog["progress_ratio"],
                    "label": definition.section,
                }
            },
        }


class TutorialCatalog:
    """Loads tutorials from a root directory.

    Expected on-disk layout (matches kanban attachments used in this repo):

      <root>/<task_id>/*.md

    If multiple .md exist under a task folder, the lexicographically first is used.
    """

    def __init__(self, *, root_dir: str | os.PathLike[str]) -> None:
        self.root_dir = Path(root_dir)

    def load(self, tutorial_id: str) -> TutorialDefinition:
        folder = self.root_dir / tutorial_id
        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Tutorial folder not found: {folder}")

        md_files = sorted(p for p in folder.glob("*.md") if p.is_file())
        if not md_files:
            raise FileNotFoundError(f"No .md tutorial files found in {folder}")

        return load_tutorial_markdown(md_files[0], tutorial_id=tutorial_id)


def load_tutorial_markdown(path: str | os.PathLike[str], *, tutorial_id: str) -> TutorialDefinition:
    p = Path(path)
    md = p.read_text(encoding="utf-8")
    fm = _extract_front_matter(md)

    title = fm.get("title") or p.stem.replace("-", " ")
    section = fm.get("section") or "Tutorial"

    steps_raw = _split_steps(md)
    steps: List[TutorialStep] = []
    for i, (heading, body) in enumerate(steps_raw):
        steps.append(TutorialStep.from_heading(step_index=i, heading=heading, body_md=body))

    if not steps:
        raise ValueError(f"No tutorial steps found in markdown: {path}")

    return TutorialDefinition(tutorial_id=tutorial_id, title=title, section=section, steps=tuple(steps))


class TutorialEngine:
    """Core orchestration for step-by-step tutorial progression."""

    def start(self, definition: TutorialDefinition) -> TutorialSession:
        first = definition.steps[0].step_id if definition.steps else None
        return TutorialSession(
            tutorial_id=definition.tutorial_id,
            current_step_id=first,
            completed_step_ids=(),
        )

    def get_current_step(self, *, session: TutorialSession, definition: TutorialDefinition) -> Optional[TutorialStep]:
        if session.current_step_id is None:
            return None
        for s in definition.steps:
            if s.step_id == session.current_step_id:
                return s
        return None

    def complete_current_step(self, *, session: TutorialSession, definition: TutorialDefinition) -> TutorialSession:
        cur = self.get_current_step(session=session, definition=definition)
        if cur is None:
            return session

        # Find next step
        next_id: Optional[str] = None
        for s in definition.steps:
            if s.step_id == cur.step_id:
                if s.step_index + 1 < definition.total_steps:
                    next_id = definition.steps[s.step_index + 1].step_id
                break

        return session.complete_step(cur.step_id, next_step_id=next_id)

    def get_context_help(self, *, session: TutorialSession, definition: TutorialDefinition, context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        """Return UI-ready help for the user's current context.

        Context sensitivity (minimal, but useful without hard-coded game metrics):
        - If the current step has checklist items, show them.
        - Otherwise, show a short quick hint derived from the step body.
        - If the user already completed the current step, prompt for next step.
        """
        context = context or {}

        cur = self.get_current_step(session=session, definition=definition)
        if cur is None:
            return {
                "state": "completed",
                "message": "Tutorial complete.",
            }

        completed = session.is_step_completed(cur.step_id)
        if completed:
            # Shouldn't usually happen because completion advances next_step_id,
            # but keep it deterministic.
            prog = session.progress(total_steps=definition.total_steps)
            return {
                "state": "next",
                "message": "You're already done with this step. Continue to the next one.",
                "current_step": cur.to_ui(),
                "progress": prog,
            }

        items = list(cur.help_items)
        hint = cur.quick_hint

        # Optional extra hints keyed off simple context.
        extra: List[str] = []
        stuck_reason = context.get("stuck_reason")
        if stuck_reason:
            extra.append(f"If you're stuck ({stuck_reason}), revisit the current step and try the checklist items above.")

        if not items and hint:
            items = [hint]

        return {
            "state": "active",
            "current_step": cur.to_ui(),
            "help": {
                "items": items,
                "extra": extra,
            },
            "progress": session.progress(total_steps=definition.total_steps),
        }


__all__ = [
    "TutorialStep",
    "TutorialDefinition",
    "TutorialSession",
    "TutorialCatalog",
    "TutorialEngine",
    "load_tutorial_markdown",
]
