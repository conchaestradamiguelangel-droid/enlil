## What does this PR do?

<!-- One sentence: what problem does it solve or what feature does it add? -->

## Related issue

Closes #<!-- issue number -->

## Checklist

- [ ] `pytest` passes (zero failures)
- [ ] If adding a god or changing routing: benchmark with `python3 enlil-bench.py` and include results
- [ ] If touching `api.py` or `orchestrator.py`: verify `enlil --review "test query"` still works
- [ ] If adding a dependency: it must be pip-installable with no system packages (or justify the exception)
- [ ] No hardcoded API keys or model names — use `.env` and the god registry

## How to test this change

<!-- Steps to reproduce or verify the fix -->
