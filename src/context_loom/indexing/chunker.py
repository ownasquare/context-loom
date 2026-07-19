"""Line-aware deterministic chunks and local hashed lexical embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_MARKDOWN_BOUNDARY = re.compile(r"^#{1,6}\s+\S")
_CODE_BOUNDARY = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|interface|type|enum|"
    r"struct|trait|impl|fn|func|record)\s+[A-Za-z_$][\w$]*"
)
_LEXICAL_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,63}")
_PROTECTED = re.compile(
    r"https?://[^\s)\]>]+|"
    r"(?<![\w/])(?:\.?\.?/)?(?:[\w.-]+/)+[\w.-]+|"
    r"`[^`\r\n]+`|"
    r"--[a-zA-Z][\w-]*|"
    r"\b[A-Z][A-Z0-9_]{2,}\b|"
    r"\b\d+(?:\.\d+)?(?:%|ms|s|MB|GB|KiB|MiB)?\b"
)
_NEGATIVE_INSTRUCTION = re.compile(
    r"(?i)\b(?:do not|don't|never|must not|cannot)\b[^\r\n.!?]{0,240}[.!?]?"
)
_DECLARED_SYMBOL = re.compile(
    r"\b(?:def|class|function|interface|type|enum|struct|trait|fn|func|record)\s+"
    r"([A-Za-z_$][\w$]*)"
)


@dataclass(frozen=True, slots=True)
class DeterministicChunk:
    ordinal: int
    text: str
    content_sha256: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    token_estimate: int
    protected_atoms: tuple[str, ...]
    embedding: tuple[float, ...]
    embedding_digest: str


def estimate_tokens(text: str) -> int:
    """Use a documented deterministic rough estimate for indexing budgets."""

    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def hashed_lexical_embedding(text: str, *, dimensions: int = 64) -> tuple[float, ...]:
    """Produce a network-free signed feature-hash vector."""

    vector = [0.0] * dimensions
    tokens = _LEXICAL_TOKEN.findall(text.casefold())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [round(value / norm, 8) for value in vector]
    return tuple(vector)


def embedding_digest(vector: tuple[float, ...]) -> str:
    encoded = json.dumps(vector, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def extract_protected_atoms(text: str) -> tuple[str, ...]:
    """Collect exact path, URL, command, label, and numeric atoms in source order."""

    located = [
        (match.start(), match.group(0).rstrip(".,;:!?")) for match in _PROTECTED.finditer(text)
    ]
    located.extend(
        (match.start(), match.group(0).strip()) for match in _NEGATIVE_INSTRUCTION.finditer(text)
    )
    located.extend((match.start(1), match.group(1)) for match in _DECLARED_SYMBOL.finditer(text))
    return tuple(dict.fromkeys(atom for _, atom in sorted(located) if atom))


def chunker_fingerprint(*, target_tokens: int, overlap_tokens: int) -> str:
    return f"deterministic-lines-v1:target={target_tokens}:overlap={overlap_tokens}:dims=64"


def _is_boundary(line: str, suffix: str) -> bool:
    if suffix in {".md", ".mdx", ".rst", ".adoc"}:
        return bool(_MARKDOWN_BOUNDARY.match(line))
    return bool(_CODE_BOUNDARY.match(line))


def _split_long_line(
    line: str,
    *,
    base_byte: int,
    line_number: int,
    target_tokens: int,
    overlap_tokens: int,
) -> list[tuple[str, int, int, int, int]]:
    """Bound minified/generated lines without cutting a UTF-8 code point."""

    byte_offsets = [0]
    for character in line:
        byte_offsets.append(byte_offsets[-1] + len(character.encode("utf-8")))
    target_bytes = max(target_tokens * 4, 4)
    overlap_bytes = max(overlap_tokens * 4, 0)
    spans: list[tuple[str, int, int, int, int]] = []
    cursor = 0
    while cursor < len(line):
        end = cursor + 1
        while end < len(line) and byte_offsets[end + 1] - byte_offsets[cursor] <= target_bytes:
            end += 1
        spans.append(
            (
                line[cursor:end],
                base_byte + byte_offsets[cursor],
                base_byte + byte_offsets[end],
                line_number,
                line_number,
            )
        )
        if end >= len(line):
            break
        next_cursor = end
        while (
            next_cursor > cursor + 1
            and byte_offsets[end] - byte_offsets[next_cursor - 1] <= overlap_bytes
        ):
            next_cursor -= 1
        cursor = max(cursor + 1, next_cursor)
    return spans


def chunk_text(
    content: str,
    relative_path: str,
    *,
    target_tokens: int = 320,
    overlap_tokens: int = 40,
) -> tuple[DeterministicChunk, ...]:
    """Split on headings/symbols, then bounded line windows with deterministic overlap."""

    if not content:
        return ()
    effective_overlap = max(0, min(overlap_tokens, target_tokens // 2))
    lines = content.splitlines(keepends=True)
    if not lines:
        lines = [content]
    suffix = PurePosixPath(relative_path).suffix.casefold()
    boundaries = [0]
    boundaries.extend(
        index for index, line in enumerate(lines[1:], start=1) if _is_boundary(line, suffix)
    )
    boundaries.append(len(lines))
    byte_offsets = [0]
    for line in lines:
        byte_offsets.append(byte_offsets[-1] + len(line.encode("utf-8")))

    windows: list[tuple[int, int]] = []
    for section_index in range(len(boundaries) - 1):
        section_start = boundaries[section_index]
        section_end = boundaries[section_index + 1]
        cursor = section_start
        while cursor < section_end:
            stop = cursor
            tokens = 0
            while stop < section_end:
                line_tokens = estimate_tokens(lines[stop])
                if stop > cursor and tokens + line_tokens > target_tokens:
                    break
                tokens += line_tokens
                stop += 1
                if tokens >= target_tokens:
                    break
            stop = max(stop, cursor + 1)
            windows.append((cursor, stop))
            if stop >= section_end:
                break
            overlap_start = stop
            overlap = 0
            while overlap_start > cursor and overlap < effective_overlap:
                overlap_start -= 1
                overlap += estimate_tokens(lines[overlap_start])
            cursor = max(cursor + 1, overlap_start)

    spans: list[tuple[str, int, int, int, int]] = []
    for start, end in windows:
        text = "".join(lines[start:end])
        if end == start + 1 and estimate_tokens(text) > target_tokens:
            spans.extend(
                _split_long_line(
                    text,
                    base_byte=byte_offsets[start],
                    line_number=start + 1,
                    target_tokens=target_tokens,
                    overlap_tokens=effective_overlap,
                )
            )
        else:
            spans.append((text, byte_offsets[start], byte_offsets[end], start + 1, end))

    chunks: list[DeterministicChunk] = []
    for ordinal, (text, start_byte, end_byte, start_line, end_line) in enumerate(spans):
        vector = hashed_lexical_embedding(text)
        chunks.append(
            DeterministicChunk(
                ordinal=ordinal,
                text=text,
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                start_byte=start_byte,
                end_byte=end_byte,
                start_line=start_line,
                end_line=end_line,
                token_estimate=estimate_tokens(text),
                protected_atoms=extract_protected_atoms(text),
                embedding=vector,
                embedding_digest=embedding_digest(vector),
            )
        )
    return tuple(chunks)
