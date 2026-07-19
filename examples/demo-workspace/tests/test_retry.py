from src.retry import should_retry


def test_authentication_failures_are_not_retried() -> None:
    assert not should_retry(401, 0)
    assert not should_retry(403, 0)


def test_transient_gateway_failure_is_bounded() -> None:
    assert should_retry(503, 2)
    assert not should_retry(503, 3)
