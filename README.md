# Sections

[![Tests](https://github.com/berkeley-cdss/sections/actions/workflows/test.yml/badge.svg)](https://github.com/berkeley-cdss/sections/actions/workflows/test.yml)
[![E2E](https://github.com/berkeley-cdss/sections/actions/workflows/e2e.yml/badge.svg)](docs/e2e.md)
[![A11y](https://github.com/berkeley-cdss/sections/actions/workflows/a11y.yml/badge.svg)](docs/a11y.md)

**Sections** is a web app for UC Berkeley courses to run their lab, discussion and tutoring sections, connected to bCourses (Canvas). Course staff set up sections, import them from a spreadsheet, manage rosters and take attendance. Students join sections and see their attendance history.

To use Sections, visit [sections.data8.org](https://sections.data8.org).

## Documentation

- **[Developing Sections](docs/developers.md):** local setup, the mock Canvas and the Canvas sandbox, roles and sign-in, and sample data.
- **[Testing](docs/testing.md):** unit tests, coverage, and the [end to end tests](docs/e2e.md) and [accessibility audit](docs/a11y.md).
- **[Database Migrations](docs/migrations.md):** changing the schema, and why PR previews can't run migrations.
- **[API](docs/api.md):** calling Sections from scripts with a course API key.

## Quick Start

Requires Python 3.14 and Node 24 (`mise install` picks both up from `mise.toml`). On Windows, use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install). From the repository root:

```
cp .env.example .env
python3 -m venv venv
source venv/bin/activate
pip install -r server/requirements.txt -r requirements-dev.txt
yarn install
flask --app server.main db upgrade
yarn dev
```

Then open `localhost:3000` and sign in as one of the mock Canvas's users. No Canvas credentials are needed. See [Developing Sections](docs/developers.md) for what each step does, and for using the Canvas sandbox.

## Canvas API Keys

The app's Canvas scopes are listed in `server/canvas_service.py`, and they must be a subset of the scopes on its Canvas developer key. bCourses API keys have strict scope and permissions, and should only be used for the exact purpose they were granted for. Specifically, the Sections API key should not be used by another app or for any purpose outside the approved scope for Sections. If you need to broaden the scope of the API key or create a new API key for a different app, contact @pancakereport to discuss. The process for obtaining a new API key requires faculty or full time staff support and a conversation with RTL, who manage bCourses. Test any change that needs a new scope against the [Canvas sandbox](docs/developers.md#canvas-sandbox) first.
