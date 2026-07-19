"""Boundary-aware deterministic analysis of a user's exact message."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from context_loom.compaction.protected_atoms import ProtectedAtomKind, extract_protected_atoms
from context_loom.domain.models import IntentProfile

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
)
_DEFAULT_ROUTES: Mapping[str, frozenset[str]] = {
    "email": frozenset({"email", "emails", "mail", "inbox"}),
    "git": frozenset({"git", "commit", "branch", "merge", "rebase", "diff"}),
    "tests": frozenset({"test", "tests", "pytest", "playwright", "cypress", "coverage"}),
    "browser": frozenset({"browser", "chrome", "website", "page", "tab"}),
    "database": frozenset({"database", "sqlite", "postgres", "mysql", "migration"}),
    "mcp": frozenset({"mcp", "tool", "tools", "server"}),
    "documentation": frozenset({"documentation", "docs", "readme", "handoff"}),
}
_LABELS: Mapping[str, frozenset[str]] = {
    "debug": frozenset({"bug", "debug", "error", "exception", "fail", "failure", "fix"}),
    "review": frozenset({"audit", "inspect", "review", "verify"}),
    "change": frozenset({"add", "build", "change", "create", "edit", "implement", "remove"}),
    "explain": frozenset({"describe", "explain", "summarize"}),
}
_RISK_WORDS: Mapping[str, frozenset[str]] = {
    "destructive": frozenset({"delete", "destroy", "drop", "erase", "purge", "reset"}),
    "security": frozenset({"credential", "password", "secret", "token", "private"}),
    "external_side_effect": frozenset({"deploy", "publish", "push", "send", "submit"}),
}


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def analyze_intent(
    message: str,
    *,
    policy_labels: Iterable[str] = (),
    route_words: Mapping[str, frozenset[str]] | None = None,
) -> IntentProfile:
    """Analyze intent using exact normalized words, never substring membership."""

    original_words = _WORD_RE.findall(message)
    normalized_words = [word.casefold() for word in original_words]
    word_set = set(normalized_words)
    atoms = extract_protected_atoms(message, policy_labels=policy_labels)

    labels = [label for label, words in _LABELS.items() if word_set.intersection(words)]
    risks = [label for label, words in _RISK_WORDS.items() if word_set.intersection(words)]
    if any(atom.kind is ProtectedAtomKind.NEGATIVE_GUARD for atom in atoms):
        risks.append("negative_guard")

    routes = route_words or _DEFAULT_ROUTES
    tool_routes = [route for route, words in routes.items() if word_set.intersection(words)]
    keywords = _ordered_unique(
        word
        for word in normalized_words
        if len(word) >= 3 and word not in _STOP_WORDS and not word.isdecimal()
    )

    return IntentProfile(
        labels=labels,
        keywords=keywords,
        explicit_paths=_ordered_unique(
            atom.text for atom in atoms if atom.kind is ProtectedAtomKind.PATH
        ),
        symbols=_ordered_unique(
            atom.text for atom in atoms if atom.kind is ProtectedAtomKind.SYMBOL
        ),
        quoted_signals=_ordered_unique(
            atom.text for atom in atoms if atom.kind is ProtectedAtomKind.QUOTED_SIGNAL
        ),
        risk_labels=_ordered_unique(risks),
        tool_routes=tool_routes,
    )
