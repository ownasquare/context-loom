"""Deterministic resource classification without importing project code."""

from __future__ import annotations

from pathlib import PurePosixPath

_INSTRUCTION_NAMES = {
    "agents.md",
    "claude.md",
    "copilot-instructions.md",
    ".cursorrules",
    ".windsurfrules",
    "gemini.md",
}
_CODE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".swift",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cs",
    ".rb",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".sql",
    ".vue",
    ".svelte",
}
_CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc"}


def classify_resource(relative_path: str) -> str:
    """Map an eligible path to the public ResourceKind string values."""

    path = PurePosixPath(relative_path)
    name = path.name.casefold()
    parts = {part.casefold() for part in path.parts}
    if name in _INSTRUCTION_NAMES or "instructions" in parts or ".rules" in parts:
        return "instruction"
    if "test" in parts or "tests" in parts or name.startswith("test_") or ".test." in name:
        return "test"
    if "validation" in parts or "evals" in parts:
        return "validation"
    if path.suffix.casefold() in _CODE_SUFFIXES:
        return "code"
    if path.suffix.casefold() in _CONFIG_SUFFIXES or name in {
        ".gitignore",
        ".contextloomignore",
        "dockerfile",
        "makefile",
    }:
        return "configuration"
    if path.suffix.casefold() in _DOC_SUFFIXES:
        return "documentation"
    return "other"


def parser_fingerprint(relative_path: str) -> str:
    """Identify the deterministic boundary strategy used for this path."""

    kind = classify_resource(relative_path)
    suffix = PurePosixPath(relative_path).suffix.casefold() or "none"
    return f"line-boundary-v1:{kind}:{suffix}"
