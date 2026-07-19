"""Deterministically extract exact strings that compaction must preserve."""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field

from context_loom.domain.models import StrictModel


class ProtectedAtomKind(StrEnum):
    """Kinds of source text whose spelling materially affects user intent."""

    PATH = "path"
    SYMBOL = "symbol"
    COMMAND = "command"
    URL = "url"
    NUMBER = "number"
    THRESHOLD = "threshold"
    QUOTED_SIGNAL = "quoted_signal"
    NEGATIVE_GUARD = "negative_guard"
    POLICY_LABEL = "policy_label"


class ProtectedAtom(StrictModel):
    """An exact protected span with its location in the original text."""

    text: str = Field(min_length=1)
    kind: ProtectedAtomKind
    start: int = Field(ge=0)
    end: int = Field(gt=0)


_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PATH_RE = re.compile(
    r"(?<![\w.])(?:[A-Za-z]:[\\/]|/|\.\.?/)?"
    r"(?:[A-Za-z0-9_.@+-]+[\\/])+[A-Za-z0-9_.@+-]+"
)
_BARE_PATH_RE = re.compile(
    r"(?<![\w.])[A-Za-z0-9_.@+-]+\."
    r"(?:adoc|bash|c|cc|cfg|conf|cpp|css|csv|go|h|html|ini|java|js|json|jsx|kt|kts|"
    r"md|mdx|php|py|pyi|rb|rs|rst|sh|sql|svelte|swift|toml|ts|tsx|txt|vue|yaml|yml|zsh)"
    r"(?!\w)",
    re.IGNORECASE,
)
_DOTTED_SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_NAMED_SYMBOL_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|[A-Z][A-Za-z0-9]+[A-Z][A-Za-z0-9]*)\b"
)
_QUOTED_RE = re.compile(r"(?P<quote>[\"'`])(?P<body>[^\n\r]*?)(?P=quote)")
_THRESHOLD_RE = re.compile(
    r"(?<!\w)(?:[<>]=?|==|!=)\s*-?\d+(?:\.\d+)?(?:\s*%|\s*[A-Za-z]{1,8})?"
    r"|(?<!\w)-?\d+(?:\.\d+)?\s*%(?!\w)"
)
_NAMED_THRESHOLD_RE = re.compile(
    r"\b(?:at\s+least|at\s+most|below|greater\s+than|less\s+than|maximum|minimum|"
    r"no\s+more\s+than|no\s+less\s+than|threshold)\s+"
    r"-?\d+(?:\.\d+)?(?:\s*%|\s*[A-Za-z]{1,8})?",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?:\s*(?:ms|s|sec|seconds?|"
    r"minutes?|hours?|kb|mb|gb|tokens?|files?|bytes?))?(?!\w)",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"\b(?:do\s+not|don't|dont|never|must\s+not|should\s+not|without)\b"
    r"[^\n.!?;]*",
    re.IGNORECASE,
)
_COMMAND_RE = re.compile(
    r"(?m)(?<!\w)(?:\$\s*)?"
    r"(?:git|uv|pytest|python(?:3)?|pip|npm|pnpm|yarn|make|docker|curl|bash|sh|"
    r"context-loom)\s+[^`\n\r;]+"
)


def _trim_url(match: re.Match[str]) -> tuple[str, int, int]:
    text = match.group(0).rstrip(".,;:!?)]}")
    return text, match.start(), match.start() + len(text)


def _matches(pattern: re.Pattern[str], text: str, kind: ProtectedAtomKind) -> list[ProtectedAtom]:
    return [
        ProtectedAtom(text=match.group(0), kind=kind, start=match.start(), end=match.end())
        for match in pattern.finditer(text)
        if match.group(0).strip()
    ]


def _path_matches(text: str) -> list[ProtectedAtom]:
    paths: list[ProtectedAtom] = []
    for match in _PATH_RE.finditer(text):
        value = match.group(0).rstrip(".,;:!?)]}")
        if value:
            paths.append(
                ProtectedAtom(
                    text=value,
                    kind=ProtectedAtomKind.PATH,
                    start=match.start(),
                    end=match.start() + len(value),
                )
            )
    return paths


def extract_protected_atoms(
    text: str,
    *,
    policy_labels: Iterable[str] = (),
) -> list[ProtectedAtom]:
    """Return protected spans in source order, de-duplicated by exact span and kind.

    Matching is deterministic and boundary-aware. Policy labels are treated literally rather
    than as regular expressions, which prevents a label from widening the match surface.
    """

    atoms: list[ProtectedAtom] = []
    occupied_source_spans: list[tuple[int, int]] = []
    for match in _URL_RE.finditer(text):
        value, start, end = _trim_url(match)
        if value:
            atoms.append(
                ProtectedAtom(text=value, kind=ProtectedAtomKind.URL, start=start, end=end)
            )
            occupied_source_spans.append((start, end))

    path_atoms = [
        atom
        for atom in _path_matches(text)
        if not any(atom.start < end and atom.end > start for start, end in occupied_source_spans)
    ]
    occupied_source_spans.extend((atom.start, atom.end) for atom in path_atoms)
    path_atoms.extend(
        atom
        for atom in _matches(_BARE_PATH_RE, text, ProtectedAtomKind.PATH)
        if not any(atom.start < end and atom.end > start for start, end in occupied_source_spans)
    )
    atoms.extend(path_atoms)
    occupied_source_spans.extend((atom.start, atom.end) for atom in path_atoms)
    atoms.extend(
        atom
        for atom in (
            *_matches(_DOTTED_SYMBOL_RE, text, ProtectedAtomKind.SYMBOL),
            *_matches(_NAMED_SYMBOL_RE, text, ProtectedAtomKind.SYMBOL),
        )
        if not any(atom.start < end and atom.end > start for start, end in occupied_source_spans)
    )
    atoms.extend(_matches(_COMMAND_RE, text, ProtectedAtomKind.COMMAND))
    atoms.extend(_matches(_THRESHOLD_RE, text, ProtectedAtomKind.THRESHOLD))
    atoms.extend(_matches(_NAMED_THRESHOLD_RE, text, ProtectedAtomKind.THRESHOLD))
    atoms.extend(_matches(_NUMBER_RE, text, ProtectedAtomKind.NUMBER))
    atoms.extend(_matches(_NEGATIVE_RE, text, ProtectedAtomKind.NEGATIVE_GUARD))

    for match in _QUOTED_RE.finditer(text):
        body = match.group("body")
        if body:
            atoms.append(
                ProtectedAtom(
                    text=body,
                    kind=ProtectedAtomKind.QUOTED_SIGNAL,
                    start=match.start("body"),
                    end=match.end("body"),
                )
            )

    for label in policy_labels:
        if not label:
            continue
        label_re = re.compile(rf"(?<!\w){re.escape(label)}(?!\w)", re.IGNORECASE)
        for match in label_re.finditer(text):
            atoms.append(
                ProtectedAtom(
                    text=match.group(0),
                    kind=ProtectedAtomKind.POLICY_LABEL,
                    start=match.start(),
                    end=match.end(),
                )
            )

    seen: set[tuple[int, int, ProtectedAtomKind]] = set()
    ordered: list[ProtectedAtom] = []
    for atom in sorted(atoms, key=lambda item: (item.start, item.end, item.kind.value)):
        key = (atom.start, atom.end, atom.kind)
        if key not in seen:
            seen.add(key)
            ordered.append(atom)
    return ordered


def protected_texts(
    text: str,
    *,
    policy_labels: Iterable[str] = (),
) -> list[str]:
    """Return exact protected strings once, retaining their first source occurrence."""

    seen: set[str] = set()
    result: list[str] = []
    for atom in extract_protected_atoms(text, policy_labels=policy_labels):
        if atom.text not in seen:
            seen.add(atom.text)
            result.append(atom.text)
    return result
