# Contributing to ENLIL

Thank you for your interest in contributing to ENLIL.

## Getting started

1. Fork the repository and clone it locally
2. Copy `.env.example` to `.env` and add your OpenRouter API key
3. Install dependencies: `pip install -r requirements.txt`
4. Run the server: `python -m uvicorn api:app --reload --port 8002`

Or with Docker:

```bash
cp .env.example .env
# edit .env with your OPENROUTER_API_KEY
docker compose up -d
```

## What we welcome

- Bug fixes with a clear description of the problem
- Performance improvements to the council or synthesis pipeline
- New god personas (see `enlil/gods/` for examples)
- Translations of the UI / decree exports
- Documentation improvements

## What to avoid

- Changes that break the post-quantum signing chain (ML-DSA-87)
- Removing the BYOK model or adding mandatory cloud dependencies
- Large refactors without prior discussion in an issue

## Reporting bugs

Open a GitHub issue with:
- Your ENLIL version (or commit hash)
- The query that triggered the bug
- Expected vs. actual output
- Logs if available (`journalctl -u enlil -n 50` or `docker compose logs enlil`)

## Pull requests

- One logical change per PR
- Include a short description of the why, not just the what
- All tests must pass before requesting review

## Code style

- Python 3.12+, type hints where practical
- No external cloud services without a self-hosted alternative
- Keep it auditable: the signing chain must be verifiable offline

## License

By contributing you agree that your code will be released under GPL-3.0.
