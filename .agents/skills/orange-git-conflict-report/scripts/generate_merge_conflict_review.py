#!/usr/bin/env python3
"""Generate a read-only HTML review report for Git merge conflicts."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import difflib
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


MARK_LEFT = "<<<<<<<"
MARK_BASE = "|||||||"
MARK_SEP = "======="
MARK_RIGHT = ">>>>>>>"

TOKEN_RE = re.compile(r"(\s+|[A-Za-z_$][A-Za-z0-9_$]*|\d+(?:\.\d+)?|.)", re.DOTALL)
CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


@dataclasses.dataclass
class ConflictHunk:
    path: str
    file_index: int
    global_index: int
    marker_start_line: int
    marker_end_line: int
    left_label: str
    right_label: str
    left_lines: list[str]
    right_lines: list[str]
    base_lines: list[str]
    left_start: int = 0
    right_start: int = 0
    proposal_start: int = 0
    proposal_lines: list[str] = dataclasses.field(default_factory=list)
    proposal_reason: str = ""
    left_stage_span: tuple[int, int] = (0, 0)
    right_stage_span: tuple[int, int] = (0, 0)
    left_base_span: tuple[int, int] = (0, 0)
    right_base_span: tuple[int, int] = (0, 0)
    left_changed_stage: set[int] = dataclasses.field(default_factory=set)
    right_changed_stage: set[int] = dataclasses.field(default_factory=set)
    proposal_span: tuple[int, int] = (0, 0)


@dataclasses.dataclass
class ConflictFile:
    path: str
    segments: list[list[str] | ConflictHunk]
    hunks: list[ConflictHunk]
    worktree_lines: list[str]
    left_lines: list[str] = dataclasses.field(default_factory=list)
    right_lines: list[str] = dataclasses.field(default_factory=list)
    proposal_lines: list[str] = dataclasses.field(default_factory=list)
    stage1_lines: list[str] = dataclasses.field(default_factory=list)
    stage2_lines: list[str] = dataclasses.field(default_factory=list)
    stage3_lines: list[str] = dataclasses.field(default_factory=list)
    left_map: list[int | None] = dataclasses.field(default_factory=list)
    right_map: list[int | None] = dataclasses.field(default_factory=list)


def run_git(repo: Path, args: list[str], *, text: bool = True) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )


def decode_bytes(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def split_lines(text: str) -> list[str]:
    lines = text.splitlines()
    if text.endswith("\n") and not lines:
        return [""]
    return lines


def git_root(repo: Path) -> Path:
    cp = run_git(repo, ["rev-parse", "--show-toplevel"])
    return Path(cp.stdout.strip())


def current_branch(repo: Path) -> str:
    try:
        name = run_git(repo, ["branch", "--show-current"]).stdout.strip()
        if name:
            return name
    except subprocess.CalledProcessError:
        pass
    try:
        return run_git(repo, ["rev-parse", "--short", "HEAD"]).stdout.strip()
    except subprocess.CalledProcessError:
        return "HEAD"


def stage_blobs(repo: Path) -> dict[str, dict[int, str]]:
    cp = run_git(repo, ["ls-files", "-u", "-z"], text=False)
    result: dict[str, dict[int, str]] = {}
    for raw in cp.stdout.split(b"\0"):
        if not raw:
            continue
        meta, raw_path = raw.split(b"\t", 1)
        mode, blob, stage = meta.decode("ascii").split()
        del mode
        path = raw_path.decode("utf-8", errors="surrogateescape")
        result.setdefault(path, {})[int(stage)] = blob
    return result


def cat_blob(repo: Path, blob: str) -> list[str]:
    cp = run_git(repo, ["cat-file", "-p", blob], text=False)
    return split_lines(decode_bytes(cp.stdout))


def parse_conflict_file(path: str, lines: list[str]) -> ConflictFile:
    segments: list[list[str] | ConflictHunk] = []
    hunks: list[ConflictHunk] = []
    context: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(MARK_LEFT):
            if context:
                segments.append(context)
                context = []
            marker_start = i + 1
            left_label = line[len(MARK_LEFT) :].strip() or "HEAD"
            i += 1
            left: list[str] = []
            base: list[str] = []
            right: list[str] = []
            side = "left"
            right_label = "incoming"
            while i < len(lines):
                current = lines[i]
                if current.startswith(MARK_BASE) and side == "left":
                    side = "base"
                    i += 1
                    continue
                if current.startswith(MARK_SEP) and side in {"left", "base"}:
                    side = "right"
                    i += 1
                    continue
                if current.startswith(MARK_RIGHT) and side == "right":
                    right_label = current[len(MARK_RIGHT) :].strip() or "incoming"
                    hunk = ConflictHunk(
                        path=path,
                        file_index=len(hunks) + 1,
                        global_index=0,
                        marker_start_line=marker_start,
                        marker_end_line=i + 1,
                        left_label=left_label,
                        right_label=right_label,
                        left_lines=left,
                        right_lines=right,
                        base_lines=base,
                    )
                    hunks.append(hunk)
                    segments.append(hunk)
                    i += 1
                    break
                if side == "left":
                    left.append(current)
                elif side == "base":
                    base.append(current)
                else:
                    right.append(current)
                i += 1
            else:
                raise ValueError(f"Unterminated conflict marker in {path} at line {marker_start}")
            continue
        context.append(line)
        i += 1
    if context:
        segments.append(context)
    return ConflictFile(path=path, segments=segments, hunks=hunks, worktree_lines=lines)


def normalize_ws(lines: Iterable[str]) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in lines if line.strip()]


def nonblank_set(lines: Iterable[str]) -> set[str]:
    return {line for line in lines if line.strip()}


def unique_union(left: list[str], right: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in [*left, *right]:
        key = line
        if key in seen:
            continue
        out.append(line)
        seen.add(key)
    return out


def note_lookup(notes: dict[str, Any], hunk: ConflictHunk) -> dict[str, Any]:
    for key in (
        str(hunk.global_index),
        f"{hunk.path}#{hunk.file_index}",
        f"{hunk.path}:{hunk.file_index}",
    ):
        value = notes.get(key)
        if isinstance(value, dict):
            return value
    return {}


def choose_proposal(hunk: ConflictHunk, mode: str, notes: dict[str, Any]) -> tuple[list[str], str]:
    note = note_lookup(notes, hunk)
    if "proposed_lines" in note:
        proposed = note["proposed_lines"]
        if not isinstance(proposed, list) or not all(isinstance(x, str) for x in proposed):
            raise ValueError(f"notes-json proposed_lines for hunk {hunk.global_index} must be a list of strings")
        return list(proposed), str(note.get("proposal_reason", "Reviewed proposal from notes JSON."))

    if mode == "ours":
        return list(hunk.left_lines), "Proposal mode is ours: keep the current-branch side."
    if mode == "theirs":
        return list(hunk.right_lines), "Proposal mode is theirs: keep the incoming-branch side."
    if mode == "union":
        return unique_union(hunk.left_lines, hunk.right_lines), "Proposal mode is union: keep a de-duplicated left-then-right union."

    left = hunk.left_lines
    right = hunk.right_lines
    if left == right:
        return list(left), "Both sides are identical; keep the shared content."
    if not left:
        return list(right), "Current branch has no conflicting lines here; keep the incoming content."
    if not right:
        return list(left), "Incoming branch has no conflicting lines here; keep the current-branch content."
    if normalize_ws(left) == normalize_ws(right):
        return list(left), "Only whitespace/formatting differs after normalization; keep the current-branch formatting."
    left_set = nonblank_set(left)
    right_set = nonblank_set(right)
    if right_set and right_set.issubset(left_set):
        return list(left), "Incoming content is already represented by the current-branch side; keep the current-branch superset."
    if left_set and left_set.issubset(right_set):
        return list(right), "Current-branch content is already represented by the incoming side; keep the incoming superset."
    return unique_union(left, right), "Both sides contain distinct content; show a de-duplicated union for review."


def build_variants(conflict_file: ConflictFile, proposal_mode: str, notes: dict[str, Any]) -> None:
    left: list[str] = []
    right: list[str] = []
    proposal: list[str] = []
    for segment in conflict_file.segments:
        if isinstance(segment, list):
            left.extend(segment)
            right.extend(segment)
            proposal.extend(segment)
            continue
        hunk = segment
        hunk.left_start = len(left)
        hunk.right_start = len(right)
        hunk.proposal_start = len(proposal)
        hunk.proposal_lines, hunk.proposal_reason = choose_proposal(hunk, proposal_mode, notes)
        left.extend(hunk.left_lines)
        right.extend(hunk.right_lines)
        proposal.extend(hunk.proposal_lines)
        hunk.proposal_span = (hunk.proposal_start, hunk.proposal_start + len(hunk.proposal_lines))
    conflict_file.left_lines = left
    conflict_file.right_lines = right
    conflict_file.proposal_lines = proposal


def build_line_map(variant: list[str], staged: list[str]) -> list[int | None]:
    if variant == staged:
        return list(range(len(variant)))
    mapping: list[int | None] = [None] * len(variant)
    matcher = difflib.SequenceMatcher(a=variant, b=staged, autojunk=False)
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(i2 - i1):
            mapping[i1 + offset] = j1 + offset
    return mapping


def insertion_index(mapping: list[int | None], start: int, staged_len: int) -> int:
    for pos in range(min(start - 1, len(mapping) - 1), -1, -1):
        mapped = mapping[pos]
        if mapped is not None:
            return min(staged_len, mapped + 1)
    for pos in range(max(0, start), len(mapping)):
        mapped = mapping[pos]
        if mapped is not None:
            return max(0, mapped)
    return min(staged_len, start)


def mapped_span(mapping: list[int | None], start: int, length: int, staged_len: int) -> tuple[tuple[int, int], set[int]]:
    if length:
        mapped = [m for m in mapping[start : start + length] if m is not None]
        if mapped:
            return (min(mapped), max(mapped) + 1), set(mapped)
    idx = insertion_index(mapping, start, staged_len)
    return (idx, idx), set()


def side_to_base_span(base_lines: list[str], side_lines: list[str], side_span: tuple[int, int]) -> tuple[int, int]:
    matcher = difflib.SequenceMatcher(a=base_lines, b=side_lines, autojunk=False)
    start_b, end_b = side_span
    relevant: list[tuple[int, int]] = []
    insert_points: list[int] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if start_b == end_b:
            touches_empty_span = b1 == b2 == start_b or b1 <= start_b <= b2
            if touches_empty_span:
                relevant.append((a1, a2))
                insert_points.append(a1)
            continue
        intersects_side = max(b1, start_b) < min(b2, end_b)
        adjacent_base_delete = b1 == b2 and start_b <= b1 <= end_b
        if intersects_side or adjacent_base_delete:
            relevant.append((a1, a2))
            insert_points.append(a1)
    if relevant:
        non_empty = [span for span in relevant if span[0] != span[1]]
        if non_empty:
            return min(span[0] for span in non_empty), max(span[1] for span in non_empty)
        point = min(insert_points) if insert_points else 0
        return point, point

    side_to_base = build_line_map(side_lines, base_lines)
    if 0 <= start_b < len(side_to_base) and side_to_base[start_b] is not None:
        point = side_to_base[start_b]
    else:
        point = insertion_index(side_to_base, start_b, len(base_lines))
    return point, point


def assign_stage_spans(conflict_file: ConflictFile) -> None:
    conflict_file.left_map = build_line_map(conflict_file.left_lines, conflict_file.stage2_lines)
    conflict_file.right_map = build_line_map(conflict_file.right_lines, conflict_file.stage3_lines)
    for hunk in conflict_file.hunks:
        hunk.left_stage_span, hunk.left_changed_stage = mapped_span(
            conflict_file.left_map,
            hunk.left_start,
            len(hunk.left_lines),
            len(conflict_file.stage2_lines),
        )
        hunk.right_stage_span, hunk.right_changed_stage = mapped_span(
            conflict_file.right_map,
            hunk.right_start,
            len(hunk.right_lines),
            len(conflict_file.stage3_lines),
        )
        hunk.left_base_span = side_to_base_span(conflict_file.stage1_lines, conflict_file.stage2_lines, hunk.left_stage_span)
        hunk.right_base_span = side_to_base_span(conflict_file.stage1_lines, conflict_file.stage3_lines, hunk.right_stage_span)


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def html_escape(text: str) -> str:
    return html.escape(text, quote=False)


def token_diff_html_classes(left: str, right: str, left_cls: str, right_cls: str) -> tuple[str, str]:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    matcher = difflib.SequenceMatcher(a=left_tokens, b=right_tokens, autojunk=False)
    left_out: list[str] = []
    right_out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_text = "".join(left_tokens[i1:i2])
        right_text = "".join(right_tokens[j1:j2])
        if tag == "equal":
            left_out.append(html_escape(left_text))
            right_out.append(html_escape(right_text))
        else:
            if left_text:
                left_out.append(f'<span class="{left_cls}">{html_escape(left_text)}</span>')
            if right_text:
                right_out.append(f'<span class="{right_cls}">{html_escape(right_text)}</span>')
    return "".join(left_out), "".join(right_out)


def token_diff_html(left: str, right: str) -> tuple[str, str]:
    return token_diff_html_classes(left, right, "inline-left", "inline-right")


def inline_diff_maps(hunk: ConflictHunk) -> tuple[dict[int, str], dict[int, str]]:
    left_map: dict[int, str] = {}
    right_map: dict[int, str] = {}
    matcher = difflib.SequenceMatcher(a=hunk.left_lines, b=hunk.right_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            count = max(i2 - i1, j2 - j1)
            for offset in range(count):
                li = i1 + offset
                ri = j1 + offset
                if li < i2 and ri < j2:
                    left_html, right_html = token_diff_html(hunk.left_lines[li], hunk.right_lines[ri])
                    left_map[li] = left_html
                    right_map[ri] = right_html
                elif li < i2:
                    left_map[li] = f'<span class="inline-left">{html_escape(hunk.left_lines[li])}</span>'
                elif ri < j2:
                    right_map[ri] = f'<span class="inline-right">{html_escape(hunk.right_lines[ri])}</span>'
        elif tag == "delete":
            for li in range(i1, i2):
                left_map[li] = f'<span class="inline-left">{html_escape(hunk.left_lines[li])}</span>'
        elif tag == "insert":
            for ri in range(j1, j2):
                right_map[ri] = f'<span class="inline-right">{html_escape(hunk.right_lines[ri])}</span>'
    return left_map, right_map


def stage_inline_map(
    hunk: ConflictHunk,
    variant_map: list[int | None],
    side: str,
    local_html: dict[int, str],
) -> dict[int, str]:
    start = hunk.left_start if side == "left" else hunk.right_start
    result: dict[int, str] = {}
    for local_idx, rendered in local_html.items():
        variant_idx = start + local_idx
        if 0 <= variant_idx < len(variant_map):
            stage_idx = variant_map[variant_idx]
            if stage_idx is not None:
                result[stage_idx] = rendered
    return result


def proposed_inline_map(hunk: ConflictHunk) -> dict[int, str]:
    result: dict[int, str] = {}
    for offset, line in enumerate(hunk.proposal_lines):
        result[hunk.proposal_start + offset] = f'<span class="inline-proposal">{html_escape(line)}</span>'
    return result


def categories(lines: list[str]) -> set[str]:
    text = "\n".join(lines)
    cats: set[str] = set()
    stripped = [line.strip() for line in lines if line.strip()]
    if not stripped:
        cats.add("empty")
    if stripped and all(line.startswith("import ") or line.startswith("static import ") for line in stripped):
        cats.add("imports")
    if stripped and all(line.startswith("//") or line.startswith("*") or line.startswith("/*") or line.endswith("*/") for line in stripped):
        cats.add("comments")
    if any(line.startswith("@") for line in stripped):
        cats.add("annotations")
    if re.search(r"\b(assert|verify|when|mock|spy|Mockito|assertThat|assertEquals)\b", text):
        cats.add("test-behavior")
    if re.search(r"\b(class|interface|enum|record|public|private|protected)\b.*[({]", text):
        cats.add("declarations")
    if re.search(r"\b(if|for|while|switch|return|throw|catch|new)\b", text):
        cats.add("executable-code")
    if re.search(r"\b(security|sandbox|permission|access|classloader|reflection|groovy|script|path|file|url)\b", text, re.I):
        cats.add("security-sensitive")
    return cats


def style_only_difference(left: list[str], right: list[str]) -> bool:
    if normalize_ws(left) == normalize_ws(right):
        return True
    left_text = "\n".join(left)
    right_text = "\n".join(right)
    without_final_left = re.sub(r"\bfinal\s+", "", left_text)
    without_final_right = re.sub(r"\bfinal\s+", "", right_text)
    without_val_left = re.sub(r"\b(val|var)\s+", "", without_final_left)
    without_val_right = re.sub(r"\b(val|var)\s+", "", without_final_right)
    return normalize_ws(without_val_left.splitlines()) == normalize_ws(without_val_right.splitlines())


def side_summary(hunk: ConflictHunk, side: str, notes: dict[str, Any]) -> str:
    note = note_lookup(notes, hunk)
    key = "left_summary" if side == "left" else "right_summary"
    if key in note:
        return str(note[key])
    own = hunk.left_lines if side == "left" else hunk.right_lines
    other = hunk.right_lines if side == "left" else hunk.left_lines
    label = "Current branch" if side == "left" else "Incoming branch"
    own_cats = categories(own)
    other_cats = categories(other)
    if not own and other:
        return f"{label} contributes no lines in this conflict and would omit {len(other)} line(s) present on the other side."
    if own and not other:
        return f"{label} contributes {len(own)} line(s) where the other side has no counterpart."
    if own == other:
        return f"{label} has the same conflicting text as the other side."
    if normalize_ws(own) == normalize_ws(other):
        return f"{label} differs only by whitespace or line formatting after normalization."
    if style_only_difference(own, other):
        return f"{label} primarily changes declaration style, such as final/val/var usage or formatting."
    if "imports" in own_cats or "imports" in other_cats:
        return f"{label} changes imports or type dependencies used by the file."
    if "annotations" in own_cats or "annotations" in other_cats:
        return f"{label} changes annotations, which can affect runtime wiring, test execution, or framework behavior."
    if "test-behavior" in own_cats or "test-behavior" in other_cats:
        return f"{label} changes test assertions, mocks, stubbing, or verification behavior."
    if "executable-code" in own_cats or "declarations" in own_cats:
        return f"{label} changes executable code or declarations with possible behavior/API impact."
    return f"{label} changes {len(own)} line(s) relative to {len(other)} line(s) on the other side."


def material_impact(path: str, hunk: ConflictHunk, notes: dict[str, Any]) -> tuple[str, str]:
    note = note_lookup(notes, hunk)
    if "material_impact" in note:
        return str(note.get("material_level", "Reviewed")), str(note["material_impact"])
    left = hunk.left_lines
    right = hunk.right_lines
    combined_cats = categories([*left, *right])
    test_path = "/test/" in path or path.endswith("Test.java") or "/src/test/" in path
    if left == right or normalize_ws(left) == normalize_ws(right) or style_only_difference(left, right):
        return "Low", "Likely formatting or style only; verify because whitespace can still matter in string literals or generated text."
    if "comments" in combined_cats and not (combined_cats - {"comments", "empty"}):
        return "Low", "Comment-only conflict; no direct runtime impact expected."
    if "imports" in combined_cats and not (combined_cats - {"imports", "empty"}):
        return "Medium", "Import-only conflict; usually compile/type-selection impact rather than direct runtime behavior."
    if test_path:
        if {"annotations", "test-behavior", "executable-code"} & combined_cats:
            return "Medium", "Material to test behavior or coverage; it may change what is exercised or asserted."
        return "Low", "Test-source conflict that appears mostly structural or stylistic."
    if "security-sensitive" in combined_cats:
        return "High", "Production conflict touches scripting, reflection, access, files, paths, or similar security-sensitive behavior."
    if {"executable-code", "declarations", "annotations"} & combined_cats:
        return "High", "Production code/declaration conflict with possible runtime behavior, API, or framework-wiring impact."
    return "Medium", "Potentially material; review the surrounding context before choosing a side."


def recommendation(hunk: ConflictHunk, notes: dict[str, Any]) -> str:
    note = note_lookup(notes, hunk)
    if "recommendation" in note:
        return str(note["recommendation"])
    return hunk.proposal_reason


def context_bounds(span: tuple[int, int], total: int, context: int) -> tuple[int, int]:
    start, end = span
    if start == end:
        return max(0, start - context), min(total, end + context + 1)
    return max(0, start - context), min(total, end + context)


def render_line_content(raw: str, rendered: str | None = None) -> str:
    if rendered is not None:
        return rendered or '<span class="empty-line"> </span>'
    if raw == "":
        return '<span class="empty-line"> </span>'
    return html_escape(raw)


def render_table(
    lines: list[str],
    changed: set[int],
    span: tuple[int, int],
    context: int,
    inline_by_index: dict[int, str] | None = None,
    *,
    empty_note: str | None = None,
) -> str:
    inline_by_index = inline_by_index or {}
    start, end = context_bounds(span, len(lines), context)
    rows: list[str] = ['<div class="code-wrap"><table class="code"><tbody>']
    inserted_note = False
    insertion = span[0] if span[0] == span[1] else None
    for idx in range(start, end):
        if insertion is not None and not inserted_note and idx >= insertion and empty_note:
            display_ln = insertion + 1 if insertion < len(lines) else len(lines) + 1
            rows.append(
                f'<tr class="empty-side"><td class="ln">{display_ln}</td>'
                f'<td class="src"><code>{html_escape(empty_note)}</code></td></tr>'
            )
            inserted_note = True
        classes = ["context"]
        if idx in changed:
            classes.append("changed")
        rendered = render_line_content(lines[idx], inline_by_index.get(idx))
        rows.append(
            f'<tr class="{" ".join(classes)}"><td class="ln">{idx + 1}</td>'
            f'<td class="src"><code>{rendered}</code></td></tr>'
        )
    if insertion is not None and not inserted_note and empty_note:
        display_ln = insertion + 1 if insertion < len(lines) else len(lines) + 1
        rows.append(
            f'<tr class="empty-side"><td class="ln">{display_ln}</td>'
            f'<td class="src"><code>{html_escape(empty_note)}</code></td></tr>'
        )
    rows.append("</tbody></table></div>")
    return "\n".join(rows)


def diff_range(start: int, end: int) -> str:
    if start == end:
        return f"{start + 1},0"
    return f"{start + 1},{end - start}"


def diff_side_row(prefix: str, line_no: int | None, content: str, row_class: str) -> str:
    line_text = "" if line_no is None else str(line_no + 1)
    rendered = content or '<span class="empty-line"> </span>'
    return (
        f'<tr class="{row_class}"><td class="diff-prefix">{html_escape(prefix)}</td>'
        f'<td class="ln">{line_text}</td><td class="src"><code>{rendered}</code></td></tr>'
    )


def render_side_by_side_diff(
    base_lines: list[str],
    side_lines: list[str],
    base_span: tuple[int, int],
    side_span: tuple[int, int],
    diff_context: int,
    from_label: str,
    to_label: str,
) -> str:
    base_start, base_end = context_bounds(base_span, len(base_lines), diff_context)
    side_start, side_end = context_bounds(side_span, len(side_lines), diff_context)
    base_slice = base_lines[base_start:base_end]
    side_slice = side_lines[side_start:side_end]
    header = f"@@ -{diff_range(base_start, base_end)} +{diff_range(side_start, side_end)} @@"
    base_rows: list[str] = [
        diff_side_row("", None, html_escape(f"{from_label} {header}"), "diff-header")
    ]
    side_rows: list[str] = [
        diff_side_row("", None, html_escape(f"{to_label} {header}"), "diff-header")
    ]
    matcher = difflib.SequenceMatcher(a=base_slice, b=side_slice, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                base_idx = base_start + i1 + offset
                side_idx = side_start + j1 + offset
                base_rows.append(diff_side_row(" ", base_idx, html_escape(base_lines[base_idx]), "diff-context"))
                side_rows.append(diff_side_row(" ", side_idx, html_escape(side_lines[side_idx]), "diff-context"))
        elif tag == "delete":
            for i in range(i1, i2):
                base_idx = base_start + i
                rendered = f'<span class="inline-remove">{html_escape(base_lines[base_idx])}</span>'
                base_rows.append(diff_side_row("-", base_idx, rendered, "diff-remove"))
                side_rows.append(diff_side_row("", None, "", "diff-empty"))
        elif tag == "insert":
            for j in range(j1, j2):
                side_idx = side_start + j
                rendered = f'<span class="inline-add">{html_escape(side_lines[side_idx])}</span>'
                base_rows.append(diff_side_row("", None, "", "diff-empty"))
                side_rows.append(diff_side_row("+", side_idx, rendered, "diff-add"))
        elif tag == "replace":
            count = max(i2 - i1, j2 - j1)
            for offset in range(count):
                base_i = i1 + offset
                side_j = j1 + offset
                if base_i < i2 and side_j < j2:
                    base_idx = base_start + base_i
                    side_idx = side_start + side_j
                    base_html, side_html = token_diff_html_classes(
                        base_lines[base_idx],
                        side_lines[side_idx],
                        "inline-change",
                        "inline-change",
                    )
                    base_rows.append(diff_side_row("-", base_idx, base_html, "diff-change"))
                    side_rows.append(diff_side_row("+", side_idx, side_html, "diff-change"))
                elif base_i < i2:
                    base_idx = base_start + base_i
                    rendered = f'<span class="inline-remove">{html_escape(base_lines[base_idx])}</span>'
                    base_rows.append(diff_side_row("-", base_idx, rendered, "diff-remove"))
                    side_rows.append(diff_side_row("", None, "", "diff-empty"))
                elif side_j < j2:
                    side_idx = side_start + side_j
                    rendered = f'<span class="inline-add">{html_escape(side_lines[side_idx])}</span>'
                    base_rows.append(diff_side_row("", None, "", "diff-empty"))
                    side_rows.append(diff_side_row("+", side_idx, rendered, "diff-add"))
    return f"""
<div class="side-by-side-diff">
  <section class="diff-side diff-side-base">
    <h5>{html_escape(from_label)}</h5>
    <div class="code-wrap"><table class="code side-diff"><tbody>
      {"".join(base_rows)}
    </tbody></table></div>
  </section>
  <section class="diff-side diff-side-target">
    <h5>{html_escape(to_label)}</h5>
    <div class="code-wrap"><table class="code side-diff"><tbody>
      {"".join(side_rows)}
    </tbody></table></div>
  </section>
</div>
"""


def stage_span_label(span: tuple[int, int], empty_prefix: str) -> str:
    start, end = span
    if start == end:
        return f"{empty_prefix} insertion point near line {start + 1}"
    return f"{start + 1}-{end}"


def render_hunk(
    conflict_file: ConflictFile,
    hunk: ConflictHunk,
    branch: str,
    context: int,
    diff_context: int,
    notes: dict[str, Any],
) -> str:
    left_local_html, right_local_html = inline_diff_maps(hunk)
    left_inline = stage_inline_map(hunk, conflict_file.left_map, "left", left_local_html)
    right_inline = stage_inline_map(hunk, conflict_file.right_map, "right", right_local_html)
    proposal_changed = set(range(hunk.proposal_span[0], hunk.proposal_span[1]))
    proposal_inline = proposed_inline_map(hunk)
    level, impact = material_impact(conflict_file.path, hunk, notes)
    left_label = stage_span_label(hunk.left_stage_span, "empty current-branch side")
    right_label = stage_span_label(hunk.right_stage_span, "empty incoming-branch side")
    proposal_label = stage_span_label(hunk.proposal_span, "empty proposed side")
    return f"""
<details class="hunk-panel">
  <summary><span>Hunk {hunk.global_index}</span><span class="summary-meta">{html_escape(conflict_file.path)} #{hunk.file_index} | worktree lines {hunk.marker_start_line}-{hunk.marker_end_line} | impact: {html_escape(level)}</span></summary>
  <div class="hunk-body">
    <div class="explanations">
      <section>
        <h4>Left side change</h4>
        <p>{html_escape(side_summary(hunk, "left", notes))}</p>
      </section>
      <section>
        <h4>Right side change</h4>
        <p>{html_escape(side_summary(hunk, "right", notes))}</p>
      </section>
      <section>
        <h4>Material impact</h4>
        <p><strong>{html_escape(level)}.</strong> {html_escape(impact)}</p>
      </section>
      <section>
        <h4>Proposed preview</h4>
        <p>{html_escape(recommendation(hunk, notes))}</p>
      </section>
    </div>
    <div class="ancestor-diffs">
      <section class="ancestor-diff">
        <h4>What changed on the left <span class="meta">closest common ancestor vs current branch, stage 1 to stage 2</span></h4>
        {render_side_by_side_diff(conflict_file.stage1_lines, conflict_file.stage2_lines, hunk.left_base_span, hunk.left_stage_span, diff_context, "Closest common ancestor", "Left/current branch")}
      </section>
      <section class="ancestor-diff">
        <h4>What changed on the right <span class="meta">closest common ancestor vs incoming branch, stage 1 to stage 3</span></h4>
        {render_side_by_side_diff(conflict_file.stage1_lines, conflict_file.stage3_lines, hunk.right_base_span, hunk.right_stage_span, diff_context, "Closest common ancestor", "Right/incoming branch")}
      </section>
    </div>
    <div class="panels">
      <section class="side left">
        <h4>Left: current branch ({html_escape(branch)} / stage 2) <span class="meta">original {html_escape(left_label)}</span></h4>
        {render_table(conflict_file.stage2_lines, hunk.left_changed_stage, hunk.left_stage_span, context, left_inline, empty_note="-- no lines on current-branch side of this conflict --")}
      </section>
      <section class="side right">
        <h4>Right: incoming branch ({html_escape(hunk.right_label)} / stage 3) <span class="meta">original {html_escape(right_label)}</span></h4>
        {render_table(conflict_file.stage3_lines, hunk.right_changed_stage, hunk.right_stage_span, context, right_inline, empty_note="-- no lines on incoming-branch side of this conflict --")}
      </section>
    </div>
    <section class="proposal">
      <h4>Proposed result preview <span class="meta">virtual proposed file lines {html_escape(proposal_label)}</span></h4>
      {render_table(conflict_file.proposal_lines, proposal_changed, hunk.proposal_span, context, proposal_inline, empty_note="-- proposed result has no lines for this hunk --")}
    </section>
  </div>
</details>
"""


def render_css() -> str:
    return """
:root {
  color-scheme: dark;
  --bg: #0b1020;
  --panel: #121a2c;
  --panel-2: #172033;
  --text: #d8dee9;
  --muted: #9aa7bd;
  --border: #2c3752;
  --left: #ff7b72;
  --right: #79c0ff;
  --proposal: #a7f3d0;
  --base: #facc15;
  --code: #0e1424;
  --kw: #c792ea;
  --str: #ecc48d;
  --num: #f78c6c;
  --comment: #6a9955;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main { width: min(1800px, calc(100vw - 32px)); margin: 0 auto; padding: 24px 0 40px; }
h1 { margin: 0 0 8px; font-size: 28px; }
h2, h3, h4, h5 { margin: 0; }
p { margin: 6px 0 0; }
.intro { color: var(--muted); margin-bottom: 18px; }
.badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.badge { border: 1px solid var(--border); background: var(--panel); padding: 5px 9px; border-radius: 6px; color: var(--muted); }
details { border: 1px solid var(--border); background: var(--panel); border-radius: 8px; margin: 12px 0; }
summary { cursor: pointer; list-style: none; padding: 12px 14px; display: flex; gap: 16px; justify-content: space-between; align-items: center; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "+"; color: var(--muted); margin-right: 8px; }
details[open] > summary::before { content: "-"; }
.summary-meta, .meta { color: var(--muted); font-size: 12px; font-weight: 400; }
.file-body, .hunk-body { border-top: 1px solid var(--border); padding: 12px; }
.hunk-panel { background: var(--panel-2); }
.explanations { display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 10px; margin-bottom: 12px; }
.explanations section { border: 1px solid var(--border); background: rgba(255,255,255,0.025); border-radius: 8px; padding: 10px; }
.explanations h4, .side h4, .proposal h4, .ancestor-diff h4, .diff-side h5 { font-size: 13px; color: #f8fafc; margin-bottom: 8px; }
.explanations p { color: var(--muted); }
.panels, .side-by-side-diff { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: stretch; }
.side, .diff-side { min-width: 0; display: flex; flex-direction: column; }
.side > .code-wrap, .diff-side > .code-wrap { flex: 1 1 auto; }
.proposal { min-width: 0; }
.proposal { margin-top: 12px; }
.ancestor-diffs { display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 12px; }
.ancestor-diff { min-width: 0; }
.code-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 6px; background: var(--code); }
table.code { width: 100%; height: 100%; border-collapse: collapse; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
td.ln { width: 1%; min-width: 54px; color: var(--muted); text-align: right; vertical-align: top; padding: 0 10px; border-right: 1px solid var(--border); user-select: none; }
td.src { white-space: pre; tab-size: 4; vertical-align: top; padding: 0 10px; min-width: 620px; }
td.diff-prefix { width: 1%; min-width: 24px; color: var(--muted); text-align: center; vertical-align: top; padding: 0 8px; border-right: 1px solid var(--border); user-select: none; }
tr.changed td.src { background: rgba(250, 204, 21, 0.06); }
tr.empty-side td.src { color: var(--muted); font-style: italic; background: rgba(148, 163, 184, 0.08); }
tr.diff-header td { color: var(--muted); background: rgba(148, 163, 184, 0.08); }
tr.diff-remove td { background: rgba(255, 123, 114, 0.12); }
tr.diff-add td { background: rgba(63, 185, 80, 0.14); }
tr.diff-change td { background: rgba(250, 204, 21, 0.13); }
tr.diff-empty td { background: rgba(148, 163, 184, 0.04); }
.inline-left { background: rgba(255, 123, 114, 0.32); outline: 1px solid rgba(255, 123, 114, 0.45); }
.inline-right { background: rgba(121, 192, 255, 0.30); outline: 1px solid rgba(121, 192, 255, 0.45); }
.inline-base { background: rgba(250, 204, 21, 0.26); outline: 1px solid rgba(250, 204, 21, 0.40); }
.inline-remove { background: rgba(255, 123, 114, 0.34); outline: 1px solid rgba(255, 123, 114, 0.48); }
.inline-add { background: rgba(63, 185, 80, 0.34); outline: 1px solid rgba(63, 185, 80, 0.48); }
.inline-change { background: rgba(250, 204, 21, 0.32); outline: 1px solid rgba(250, 204, 21, 0.46); }
.inline-proposal { background: rgba(167, 243, 208, 0.18); outline: 1px solid rgba(167, 243, 208, 0.28); }
.empty-line { display: inline-block; min-width: 1ch; }
.tok-keyword { color: var(--kw); font-weight: 600; }
.tok-string { color: var(--str); }
.tok-number { color: var(--num); }
.tok-comment { color: var(--comment); font-style: italic; }
@media (max-width: 1100px) {
  .panels, .side-by-side-diff, .explanations { grid-template-columns: 1fr; }
  td.src { min-width: 520px; }
}
"""


def render_highlighter_script() -> str:
    return r"""
(() => {
  const keywords = new Set('abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while var record sealed permits non-sealed true false null'.split(' '));
  const tokenRe = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/.*|\/\*.*?\*\/|\b[A-Za-z_$][A-Za-z0-9_$]*\b|\b\d+(?:\.\d+)?\b)/g;
  function cls(token) {
    if (token.startsWith('//') || token.startsWith('/*')) return 'tok-comment';
    if (token.startsWith('"') || token.startsWith("'")) return 'tok-string';
    if (/^\d/.test(token)) return 'tok-number';
    if (keywords.has(token)) return 'tok-keyword';
    return '';
  }
  function replaceTextNode(node) {
    const text = node.nodeValue;
    if (!text || !tokenRe.test(text)) {
      tokenRe.lastIndex = 0;
      return;
    }
    tokenRe.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const match of text.matchAll(tokenRe)) {
      if (match.index > last) frag.appendChild(document.createTextNode(text.slice(last, match.index)));
      const token = match[0];
      const klass = cls(token);
      if (klass) {
        const span = document.createElement('span');
        span.className = klass;
        span.textContent = token;
        frag.appendChild(span);
      } else {
        frag.appendChild(document.createTextNode(token));
      }
      last = match.index + token.length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    node.replaceWith(frag);
  }
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      replaceTextNode(node);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE || node.className?.startsWith?.('tok-')) return;
    Array.from(node.childNodes).forEach(walk);
  }
  document.querySelectorAll('td.src code').forEach(walk);
})();
"""


def render_report(
    files: list[ConflictFile],
    branch: str,
    context: int,
    diff_context: int,
    notes: dict[str, Any],
    proposal_mode: str,
) -> str:
    hunk_count = sum(len(f.hunks) for f in files)
    generated = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    file_blocks: list[str] = []
    for conflict_file in files:
        hunks = "\n".join(render_hunk(conflict_file, h, branch, context, diff_context, notes) for h in conflict_file.hunks)
        file_blocks.append(
            f"""
<details class="file-block">
  <summary><span>{html_escape(conflict_file.path)}</span><span class="summary-meta">{len(conflict_file.hunks)} hunk(s)</span></summary>
  <div class="file-body">
    {hunks}
  </div>
</details>
"""
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Merge Conflict Review</title>
<style>
{render_css()}
</style>
</head>
<body>
<main>
  <h1>Merge Conflict Review</h1>
  <p class="intro">Generated {html_escape(generated)}. This report is review-only and did not apply any merge resolution. Inline highlights mark changed words, substrings, and whitespace where possible.</p>
  <div class="badge-row">
    <span class="badge">Files: {len(files)}</span>
    <span class="badge">Hunks: {hunk_count}</span>
    <span class="badge">Context: {context} lines</span>
    <span class="badge">Diff context: {diff_context} lines</span>
    <span class="badge">Proposal mode: {html_escape(proposal_mode)}</span>
    <span class="badge">Left: current branch / stage 2</span>
    <span class="badge">Right: incoming branch / stage 3</span>
  </div>
  {"".join(file_blocks)}
</main>
<script>
{render_highlighter_script()}
</script>
</body>
</html>
"""


def load_notes(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("--notes-json must contain a JSON object")
    return data


def collect_conflicts(repo: Path, proposal_mode: str, notes: dict[str, Any]) -> list[ConflictFile]:
    blobs = stage_blobs(repo)
    paths = sorted(path for path, stages in blobs.items() if 1 in stages and 2 in stages and 3 in stages)
    files: list[ConflictFile] = []
    global_index = 1
    for relpath in paths:
        worktree_path = repo / relpath
        if not worktree_path.exists():
            continue
        text = worktree_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_conflict_file(relpath, split_lines(text))
        if not parsed.hunks:
            continue
        for hunk in parsed.hunks:
            hunk.global_index = global_index
            global_index += 1
        parsed.stage1_lines = cat_blob(repo, blobs[relpath][1])
        parsed.stage2_lines = cat_blob(repo, blobs[relpath][2])
        parsed.stage3_lines = cat_blob(repo, blobs[relpath][3])
        build_variants(parsed, proposal_mode, notes)
        assign_stage_spans(parsed)
        files.append(parsed)
    return files


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate merge-conflict-review.html without resolving conflicts.")
    parser.add_argument("--repo", default=".", help="Git repository root or any path inside it. Default: current directory.")
    parser.add_argument("--output", default="merge-conflict-review.html", help="Output HTML path. Relative paths are resolved under the repo root.")
    parser.add_argument("--context", type=int, default=15, help="Context lines around each hunk. Default: 15.")
    parser.add_argument("--diff-context", type=int, default=15, help="Context lines in each ancestor side-by-side diff. Default: 15.")
    parser.add_argument("--proposal", choices=["auto", "ours", "theirs", "union"], default="auto", help="Review-only proposed preview strategy.")
    parser.add_argument("--notes-json", type=Path, help="Optional reviewed hunk notes and proposed_lines overrides.")
    parser.add_argument("--allow-clean", action="store_true", help="Write an empty no-conflicts report instead of failing when no conflicts are found.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo = git_root(Path(args.repo).resolve())
    output = Path(args.output)
    if not output.is_absolute():
        output = repo / output
    if args.context < 0:
        raise ValueError("--context must be non-negative")
    if args.diff_context < 0:
        raise ValueError("--diff-context must be non-negative")
    notes = load_notes(args.notes_json)
    files = collect_conflicts(repo, args.proposal, notes)
    if not files and not args.allow_clean:
        print("No unmerged Git index stages with conflict markers were found.", file=sys.stderr)
        return 2
    report = render_report(files, current_branch(repo), args.context, args.diff_context, notes, args.proposal)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output} ({len(files)} file(s), {sum(len(f.hunks) for f in files)} hunk(s))")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        print(stderr.strip() or str(exc), file=sys.stderr)
        raise SystemExit(exc.returncode or 1)
