# Demo workspace instructions

- Preserve the `MAX_RETRIES = 3` policy.
- Do not retry HTTP 401 or 403 responses.
- Run `python -m pytest tests/test_retry.py` after changing retry behavior.
