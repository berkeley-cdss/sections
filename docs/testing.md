# Testing

Tests live in `tests/`: `tests/unit/` holds tests that use Flask's test client against an in-memory SQLite database, `tests/e2e/` uses the app in a browser as students and staff do ([e2e.md](e2e.md)), and `tests/a11y/` audits every page's accessibility in a browser ([a11y.md](a11y.md)). The browser tests share their server, seed data and helpers (`tests/browser.py`). `server/` is a package, and `pytest.ini` puts the repository root on the import path, so tests import the app's modules the way the app does (`from server.models import db`). `pytest` from the repository root runs the unit tests, `pytest tests/e2e` the end to end tests, and `pytest tests/a11y` the a11y audit.

The browser tests need Chrome and the frontend build in `server/static/`, where the app serves the course pages from, as in the Docker image. `server/static/` is gitignored, so a fresh checkout has no build there. Build the frontend and copy it in yourself, and again after any frontend change:

```
yarn build && cp -R build/. server/static/
```

CI does this itself in `.github/workflows/e2e.yml` and `.github/workflows/a11y.yml`.

## Writing Tests

Tests build the app with the same `create_app` (`server/application.py`) that `server/main.py` uses, given a test config, so they test the app as it's deployed:
- New tests can be plain functions using the pytest fixtures in `tests/conftest.py` (`app`, `client`).
- Most existing tests are `unittest` classes built on `tests/unit/support.py`. `AppTestCase` gives an empty database and request helpers, and `CourseTestCase` adds two offerings, a staff member, a student and a lab in each.

Put a test in the file for what it tests (`test_login.py`, `test_sheet_imports.py`, `test_section_settings.py`, ...), and add a file when nothing fits. Unit test files go in `tests/unit/` and are named `test_<subject>.py`, with test functions and methods named `test_<what it checks>`. Plain `pytest` only collects `tests/unit/` (`testpaths` in `pytest.ini`), and CI runs `tests/e2e/` and `tests/a11y/` by name, so a test file anywhere else, such as `server/`, never runs, locally or in CI.

## Coverage

CI uploads coverage of `server/` to [Codecov](https://app.codecov.io/gh/berkeley-cdss/sections), whose `codecov/project` check fails a PR that lowers coverage below main's (`codecov.yml`). Its PR comment also says how much of the PR's changed lines are tested. Separately, the tests job fails if coverage drops below 74%, its level when that minimum was set.
