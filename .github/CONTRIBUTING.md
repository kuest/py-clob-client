# Contribution Guide

Contributions to `kuest-py-clob-client` are welcome. This document outlines the basic workflow for local development and pull requests.

## Getting Started

1. Fork `kuest/py-clob-client`.
2. Clone your fork.
3. Use Python 3.10 or newer. CI currently runs on Python 3.10.
4. Create and activate a virtual environment, then install dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Open pull requests against the `main` branch and fill out the PR template.

## Local Checks

Before submitting a PR for review, run the same checks used by CI:

```sh
python -m black --check .
python -m pytest -s
python -m pip install build
python -m build --sdist --wheel
```

You can format the codebase with:

```sh
python -m black .
```

## Branch Structure & Naming

The `main` branch represents the current development state of the codebase. All pull requests should target `main`.

Use clear branch names and follow the [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) style for PR titles and commit subjects, such as `fix:`, `feat:`, `docs:`, `test:`, `refactor:`, and `chore:`.

## Change Guidelines

- Keep PRs focused on one feature, bugfix, or maintenance change.
- Add or update tests for behavior changes whenever feasible.
- Update `README.md`, examples, and Python packaging metadata when public SDK behavior changes.
- Commit `requirements.txt` changes when dependencies change.
- Do not include secrets, private keys, or real API credentials in examples, tests, logs, or PR descriptions.
- Review your own diff before requesting review.
