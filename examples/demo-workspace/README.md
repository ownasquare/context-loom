# Acme retry service

The request client retries transient gateway errors three times with exponential backoff.
The implementation lives in `src/retry.py`; tests are in `tests/test_retry.py`.

## Safety

Never retry authentication failures or destructive requests.
