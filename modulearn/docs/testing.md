# Testing Strategy

## Current focus

The test suite is now centered on high-value regression checks:

- smoke rendering for major routes
- dashboard access and role behavior
- enrollment signal behavior
- progress rollups and event-ledger writes
- invite/self-enrollment idempotence
- outbound LTI outcome compatibility

## App-level coverage

### `main/tests.py`

- marketing page render smoke tests

### `accounts/tests.py`

- login/signup/profile route coverage
- profile auth guard

### `courses/tests.py`

- enrollment signal bootstrapping
- progress completion timestamps
- course rollups
- invite enrollment flow

### `dashboard/tests.py`

- student dashboard render
- instructor dashboard render
- role redirection behavior

### `lti/tests.py`

- existing outbound tool-consumer launch/outcome behavior
- new local progress and timeline integration coverage

## Recommended commands

```bash
python manage.py test
python manage.py test courses
python manage.py test dashboard
python manage.py test lti
```

## Notes

- The local shell in this workspace may not have a configured Python interpreter, so tests may need to run through Docker or another provisioned environment.
- Treat the test suite as compatibility protection during the ongoing package merge and template consolidation.
