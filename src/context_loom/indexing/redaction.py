"""Deterministic secret-value redaction for otherwise eligible text files."""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTION_MARKER = "<REDACTED>"

_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----.*?"
    r"-----END [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----",
    re.DOTALL,
)
_BEARER = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_KNOWN_TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})\b"
)
_CREDENTIAL_KEY = (
    r"[A-Za-z0-9_.-]{0,96}(?:api[_-]?key|token|password|passwd|secret|"
    r"secret[_-]?access[_-]?key|client[_-]?secret|private[_-]?key|"
    r"signing[_-]?key|credential|connection[_-]?string)"
)
_ASSIGNMENT = re.compile(rf"(?im)(\b{_CREDENTIAL_KEY}\b\s*[=:]\s*)([^\s,;#\"']{{4,}})")
_QUOTED_ASSIGNMENT = re.compile(
    rf"(?im)(\b{_CREDENTIAL_KEY}\b\s*[=:]\s*)([\"'])([^\"'\r\n]{{4,}})([\"'])"
)
_JSON_ASSIGNMENT = re.compile(
    rf"(?i)([\"']{_CREDENTIAL_KEY}[\"']\s*:\s*[\"'])"
    r"([^\"'\r\n]{4,})([\"'])"
)
_CLI_ASSIGNMENT = re.compile(
    r"(?i)(--(?:api[-_]?key|token|password|secret|client[-_]?secret|credential)"
    r"(?:=|\s+))([\"']?)([^\s,;\"']{4,})([\"']?)"
)
_JSON_CLI_PAIR = re.compile(
    r"(?i)([\"']--(?:api[-_]?key|token|password|secret|client[-_]?secret|credential)"
    r"[\"']\s*,\s*[\"'])([^\"'\r\n]{4,})([\"'])"
)
_URI_PASSWORD = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]{1,20}://[^\s/:@]+:)([^\s/@]{3,})(@)")


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Sanitized text plus non-sensitive audit information."""

    text: str
    count: int
    reasons: tuple[str, ...]


def _replace_pem(match: re.Match[str]) -> str:
    newline_count = match.group(0).count("\n")
    return "<REDACTED_KEY_BLOCK>" + "\n" * newline_count


def redact_secrets(text: str) -> RedactionResult:
    """Remove credential values while retaining key names and line positions."""

    reasons: list[str] = []
    count = 0

    def apply(pattern: re.Pattern[str], replacement: str | object, reason: str) -> None:
        nonlocal count, text
        updated, substitutions = pattern.subn(replacement, text)  # type: ignore[arg-type]
        if substitutions:
            text = updated
            count += substitutions
            reasons.append(reason)

    apply(_PEM_BLOCK, _replace_pem, "private_key_block")
    apply(_BEARER, rf"\1{REDACTION_MARKER}", "bearer_token")

    apply(
        _QUOTED_ASSIGNMENT,
        rf"\1\2{REDACTION_MARKER}\4",
        "credential_assignment",
    )
    apply(_ASSIGNMENT, rf"\1{REDACTION_MARKER}", "credential_assignment")
    apply(_JSON_ASSIGNMENT, rf"\1{REDACTION_MARKER}\3", "credential_field")
    apply(_CLI_ASSIGNMENT, rf"\1\2{REDACTION_MARKER}\4", "credential_argument")
    apply(_JSON_CLI_PAIR, rf"\1{REDACTION_MARKER}\3", "credential_argument")
    apply(_URI_PASSWORD, rf"\1{REDACTION_MARKER}\3", "credential_uri")
    apply(_KNOWN_TOKEN, REDACTION_MARKER, "known_token_format")
    return RedactionResult(text=text, count=count, reasons=tuple(dict.fromkeys(reasons)))
