# Contributing to Resonance Music Builder

Thank you for your interest in contributing to **Resonance Music Builder**.
Contributions of all kinds are welcome, including bug reports, feature requests, documentation improvements, and code enhancements.

This document outlines the contribution process and expectations.

---

## How to Contribute

### Reporting Bugs

Before opening a new issue:

1. Check the existing [Issues](../../issues) to avoid duplicates.
2. If the issue has not been reported, create a new issue including:
    - A clear and descriptive title
    - Steps to reproduce the issue
    - Expected behavior vs. actual behavior
    - Operating system and Python version
    - Relevant logs or error messages (if applicable)

Well-documented bug reports help issues get resolved faster.

---

### Suggesting Features

Feature suggestions are welcome if they align with the project’s goals.

To propose a feature:

1. Open a new issue with the `enhancement` label
2. Describe the feature clearly
3. Explain the use case and motivation
4. Mention any potential drawbacks or alternatives, if relevant

Note: Features that significantly increase legal, ethical, or maintenance risk may be declined.

---

### Pull Requests

To submit a Pull Request (PR):

1. Fork the repository
2. Create a new branch from `main`:

    ```bash
    git checkout -b feature/your-feature-name
    ```

3. Make your changes
4. Test thoroughly (see Testing section)
5. Commit using clear, conventional commit messages
6. Push your branch:

    ```bash
    git push origin feature/your-feature-name
    ```

7. Open a Pull Request describing:
    - What was changed
    - Why the change is needed
    - Any relevant issue references

Small, focused PRs are preferred over large, multi-purpose ones.

---

## Code Style Guidelines

This project uses automated formatting tools:

- **Black** – Code formatting (line length: 120)
- **isort** – Import sorting (profile: black)
- **flake8** – Linting
- **mypy** – Type checking (optional)

### Before committing:

```bash
# Format code
black src/ tests/ --line-length 120
isort src/ tests/ --profile black --line-length 120

# Run tests
pytest tests/ -v
```

### General guidelines:

- Follow **PEP 8** style guidelines
- Add docstrings to public functions and classes
- Keep functions small and focused
- Use type hints where reasonable
- Avoid introducing unnecessary dependencies

Consistency and readability are prioritized over micro-optimizations.

---

## Code Structure (v7.x)

The project follows a domain-driven modular architecture:

- `src/resonance_audio_builder/core`: Configuration, Builder, App state.
- `src/resonance_audio_builder/audio`: Downloader, Metadata, Analysis, Lyrics.
- `src/resonance_audio_builder/network`: Networking primitives, Cache, Rate limiting.
- `src/resonance_audio_builder/watch`: Watchdog observer.

Please place new code in the appropriate module.

---

## Commit Message Format

Use a conventional commit format:

```
type: short summary

optional longer explanation
```

Allowed types:

- `feat` – New functionality
- `fix` – Bug fixes
- `docs` – Documentation changes
- `style` – Formatting or style-only changes
- `refactor` – Code restructuring without behavior change
- `test` – Adding or improving tests
- `chore` – Maintenance or tooling changes

Example:

```
feat: add retry logic for failed downloads
```

---

## Testing Requirements

Before submitting a PR:

### Run the test suite:

```bash
pytest tests/ -v
```

### Manual testing:

1. Run the application with a small CSV dataset
2. Test all relevant menu options
3. Verify that progress persistence works correctly
4. Confirm no regressions in existing functionality
5. Ensure the application exits cleanly on interruption

If applicable, add or update unit tests.

---

## Legal and Responsibility Notice

Contributors must ensure that:

- Code does not intentionally bypass platform protections
- No copyrighted content is included in the repository
- No credentials, cookies, or personal data are committed

All contributions must comply with applicable laws and platform terms.

---

## Questions or Discussion

If you have questions or need clarification:

- Open an issue using the `question` label
- Be specific and provide context when possible

---

Thank you for helping improve Resonance Music Builder.
Your contributions make the project better, more reliable, and more maintainable.
