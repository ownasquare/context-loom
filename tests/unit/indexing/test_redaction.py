from __future__ import annotations

from context_loom.indexing.redaction import REDACTION_MARKER, redact_secrets


def test_redaction_handles_known_tokens_bearer_and_uris() -> None:
    source = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
        "token=" + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n"
        "db=postgresql://user:hunter2@example.test/app\n"
    )
    result = redact_secrets(source)

    assert "abcdefghijklmnopqrstuvwxyz" not in result.text
    assert "hunter2" not in result.text
    assert result.text.count(REDACTION_MARKER) == 3
    assert result.count == 3


def test_private_key_redaction_preserves_line_count() -> None:
    source = (
        "before\n-----BEGIN "
        + "PRIVATE KEY-----\nabc\ndef\n-----END "
        + "PRIVATE KEY-----\nafter\n"
    )
    result = redact_secrets(source)

    assert "abc" not in result.text
    assert result.text.count("\n") == source.count("\n")
    assert result.reasons == ("private_key_block",)


def test_redaction_removes_shell_and_json_credential_arguments() -> None:
    source = 'command --api-key shell-secret\n["--token", "json-secret"]\n'
    result = redact_secrets(source)

    assert "shell-secret" not in result.text
    assert "json-secret" not in result.text
    assert result.text.count(REDACTION_MARKER) == 2
