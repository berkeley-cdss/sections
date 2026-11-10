# Sections

[![A11y](https://github.com/berkeley-cdss/sections/actions/workflows/a11y.yml/badge.svg)](docs/a11y.md)


## Local Development Set Up

Requires Python 3.14 and Node 24 (`mise install` picks both up from `mise.toml`), and Chrome for the browser tests. The frontend is React 19 and TypeScript, built with Vite.

1. Copy `.env.example` to `.env`. Never commit `.env`. By default the app mocks Canvas, so no Canvas credentials are needed (see [Mock Canvas](#mock-canvas)); to use the [Canvas sandbox](#canvas-sandbox) instead, set `MOCK_CANVAS=false` and fill in its `CANVAS_CLIENT_ID` and `CANVAS_CLIENT_SECRET` (ask a maintainer).
2. Create a virtual environment and install the server dependencies:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r server/requirements.txt
   ```
3. Install the frontend dependencies with `yarn install`.
4. Create or update the local database with `flask --app server.main db upgrade` from the repository root. `server/` is a package, so run the app's commands from the root, as below.
5. Run both with `yarn dev`, or separately: the backend with `python3 -m server.main` (port 8000) and the frontend with `yarn start` (the Vite dev server on port 3000, which forwards API calls, the login routes and `/offerings` to port 8000).
6. Install the test dependencies with `pip install -r requirements-dev.txt`, then run the backend tests with `pytest` from the repository root (see [Tests](#tests)).

## Tests

Tests live in `tests/`, as in seating: `tests/unit/` holds tests that use Flask's test client against an in-memory SQLite database, `tests/e2e/` uses the app in a browser as students and staff do ([docs/e2e.md](docs/e2e.md)), and `tests/a11y/` audits every page's accessibility in a browser ([docs/a11y.md](docs/a11y.md)). The browser tests share their server, seed data and helpers (`tests/browser.py`). `server/` is a package, and `pytest.ini` puts the repository root on the import path, so tests import the app's modules the way the app does (`from server.models import db`). `pytest` from the repository root runs the unit tests, `pytest tests/e2e` the end to end tests, and `pytest tests/a11y` the a11y audit. CI runs each on Python 3.14, the version the Dockerfile uses: the unit tests in `.github/workflows/test.yml`, which adds a coverage report to the run's summary page, and the browser tests in `e2e.yml` and `a11y.yml`.

The browser tests need Chrome and the frontend build in `server/static/`, where the app serves the course pages from, as in the Docker image. `server/static/` is gitignored, so a fresh checkout has no build there. Build the frontend and copy it in yourself, and again after any frontend change:

```
yarn build && cp -R build/. server/static/
```

CI does this itself in `e2e.yml` and `a11y.yml`.

Tests build the app with the same `create_app` (`server/application.py`) that `server/main.py` uses, given a test config, so they test the app as it's deployed:
- New tests can be plain functions using the pytest fixtures in `tests/conftest.py` (`app`, `client`), like seating's tests.
- Most existing tests are `unittest` classes built on `tests/unit/support.py`. `AppTestCase` gives an empty database and request helpers, and `CourseTestCase` adds two offerings, a staff member, a student and a lab in each.

Put a test in the file for what it tests (`test_login.py`, `test_sheet_imports.py`, `test_section_settings.py`, ...), and add a file when nothing fits. Unit test files go in `tests/unit/` and are named `test_<subject>.py`, with test functions and methods named `test_<what it checks>`. Plain `pytest` only collects `tests/unit/` (`testpaths` in `pytest.ini`), and CI runs `tests/e2e/` and `tests/a11y/` by name, so a test file anywhere else, such as `server/`, never runs, locally or in CI.

CI uploads coverage of `server/` to [Codecov](https://app.codecov.io/gh/berkeley-cdss/sections), whose `codecov/project` check fails a PR that lowers coverage below main's (`codecov.yml`). Its PR comment also says how much of the PR's changed lines are tested. Separately, the tests job fails if coverage drops below 74%, its level when that minimum was set.

## Authentication

One deployment serves every bCourses course, with the same routes as seating. Users log in through Canvas OAuth (`/login/`, which returns to `/authorized/`), and `/offerings` lists their courses. Each course offering lives under `/offerings/<canvas course id>/`. Roles come from each Canvas enrollment at sign-in: Teachers and TAs are staff, and Teachers and Lead TAs are admins. Members of the `ADMIN_OVERRIDE_CANVAS_COURSE_ID` course are staff and admin everywhere. Someone added to a course after signing in needs to sign out and in again.

Course staff set up Sections for a course with "Import courses from Canvas" (`/offerings/new`). Offerings moved from the monorepo store their data under an old key (`cs61a`, `data8`, ...); link each one to its Canvas course with `flask --app server.main link-offering <canvas id> <key> "<name>"`, run from the repository root against that database.

Locally, Canvas is either mocked (the default) or the Canvas sandbox (`MOCK_CANVAS=false`). Mocking is easiest for most work. If you are making changes that require a change to the Canvas key, you should ensure the changes work locally using the Canvas sandbox before requesting a change to the production key.

### Mock Canvas

As in seating, development mocks Canvas unless `MOCK_CANVAS=false`, so a fresh checkout can be signed into without any Canvas credentials, and tests can sign in without reaching Canvas. Logging in goes to `/dev_login/`, which lists the mock Canvas's users and their roles in each course; pick one to sign in as them. To try the staff, admin or student views, sign in as a user with that role: Oski Bear is a teacher, and so an admin, in COMPSCI 169A (Canvas course `1234567`). The users, courses and enrollments are in `server/fake_canvas_data/` (the same users and courses as seating's, plus Oski Bear, so that admin pages can be tried), and `server/fake_canvas.py` answers the Canvas calls in `server/canvas_service.py` from them. Staff can import those courses with "Import courses from Canvas" and add their students by email as usual. Staging and production never mock Canvas, whatever `MOCK_CANVAS` says, and `/dev_login/` redirects home whenever Canvas isn't mocked.

To fill a course with sections, see [Sample Sections](#sample-sections).

### Canvas Sandbox

The production Sections app is deployed on GCP Cloud Run and talks to bCourses, UC Berkeley's Canvas. The Canvas sandbox, [ucberkeleysandbox.instructure.com](https://ucberkeleysandbox.instructure.com/), is a separate, real Canvas instance for testing, with its own developer key, so local development never needs the production key. Talk to maintainers to be added to the Canvas sandbox. You'll be an admin there, so you can view the development key and create new keys as needed.

You can do anything you'd like in the sandbox to simulate your desired testing environment (create courses, add students, specify user roles, etc.). To try the staff, admin or student views, give your sandbox account that role in a course. You can make your own course, but we currently have a course set up with users, which you can find (after signing in) by clicking the "Admin" button on the sidebar, then "UC Berkeley Sandbox". Search through the courses for the one titled "Mango 101 (Deokpy Section)".

To sign in locally against the sandbox, open `localhost:3000/offerings` and log in. This works on port 3000 if the sandbox developer key allows `http://localhost:3000/authorized/` as a redirect URI. Otherwise, log in at `localhost:8000/login/` instead, then go back to `localhost:3000`. A "template not found" error for course pages on port 8000 is expected: in development, the course pages are served by the Vite dev server on port 3000, not by the backend.

### More About Accessing Canvas APIs

Our wrapper for the Canvas API is `server/canvas_service.py`, which also lists the scopes the app requests at login. Those scopes must match the scopes on the app's Canvas developer key.

bCourses API keys have strict scope and permissions. bCourses API keys should only be used for the exact purpose they were granted for. Specifically, the sections app API key should not be used by another app or for any purpose outside the approved scope for the sections app. If you need a new API key with broader scope or for a different app, please contact @pancakereport to discuss. The process for obtaining a new API key requires faculty or full time staff (like @pancakereport) support and working with RTL who manage bCourses.

## Sample Sections

There are two ways to fill a local course with sections. Both run from the repository root, without the server running, and both add to the same course if you use both:

- **Demo data:** `python3 -m server.seed <canvas course id>` sets up the course in Sections if it isn't already (naming it "Demo 101"), then adds 100 discussion and 100 lab sections and 200 made-up students. It does nothing outside development.
- **Example CSVs:** `python3 -m server.import_locally` imports the sections and enrollment in `server/test_csvs/`, as staff would from a spreadsheet. The course must be set up in Sections first, with "Import courses from Canvas" or the seed.

### With the mock Canvas

Use COMPSCI 169A (Canvas course `1234567`), where Oski Bear is a teacher.

1. Set up the course: sign in as Oski Bear and use "Import courses from Canvas" on `localhost:3000/offerings`, or run `python3 -m server.seed 1234567`.
2. Optionally, import the example CSVs:

   ```
   python3 -m server.import_locally --course 1234567 --type sections --file server/test_csvs/test_sections.csv
   python3 -m server.import_locally --course 1234567 --type enrollment --file server/test_csvs/disc_enrollment.csv
   python3 -m server.import_locally --course 1234567 --type enrollment --file server/test_csvs/lab_enrollment.csv
   ```

3. Signed in as Oski Bear, open `localhost:3000/offerings/1234567/`; you should see the sections.

### With the Canvas sandbox

Use "Mango 101 (Deokpy Section)" (Canvas course `157` on the sandbox), with `MOCK_CANVAS=false`. Your sandbox account needs a role in that course to open it.

1. Set up the course: sign in and use "Import courses from Canvas" on `localhost:3000/offerings`, or run `python3 -m server.seed 157`.
2. Optionally, import the example CSVs, as above with `--course 157`.
3. Open `localhost:3000/offerings/157/`; you should see the sections.

## Database Migrations

The schema is managed with Flask-Migrate (Alembic); migrations live in `server/migrations/versions`. To change the schema, edit `server/models.py`, then from the repository root:

```
flask --app server.main db migrate -m "describe the change"   # generates a migration; review and edit it
flask --app server.main db upgrade                             # applies it to your local database
```

Commit the migration with the model change. Deployments with `RUN_MIGRATIONS=true` (staging and production) run `flask db upgrade` when they start; PR previews never do, because they share the staging database.

### Migrations and PR previews

Sections checks that the database's migration matches the code's latest migration (`server/schema_check.py`). While they differ, every page, API call and `/health` returns 503 with a message saying why, rather than failing on the first query that uses a missing column. The check is repeated at most once a minute.

This means **a PR that adds a migration can't be tried on its preview.** The preview shares the staging database, which only gets the migration when the PR is merged and staging deploys, so the preview shows "This is a preview of PR #N, which adds a database migration… Merge the PR to see its changes on staging." Test such a PR locally (`flask --app server.main db upgrade` against your own database), then merge it and check staging.

The reverse also happens: after another PR with a migration is merged, staging's database is ahead of a preview whose branch doesn't have that migration. The preview then says to merge main into the PR's branch, which redeploys the preview with the migration.

Locally, the same check tells you to run `flask --app server.main db upgrade` when your database is behind, for example after pulling a new migration.

## API
Functions marked with the `@api` decorator are also exposed at `/offerings/<canvas course id>/api/sudo/<name>`, for scripts. Each request needs an API key, which a course admin (an instructor or Lead TA in bCourses) makes on the course's Admin page, under API Keys. A key:

- works only in the course it was made in, and only while its owner is an admin there;
- stops working if its owner hasn't signed in to Sections for 7 days (`API_KEY_ROLE_MAX_AGE`, in seconds), because bCourses roles are only read at sign-in. Signing in again starts it working;
- runs the function as its owner, or as the course member whose `email` the request names; never as anyone outside the course;
- can't list, create, revoke or rotate keys. Do that on the Admin page, where any admin can revoke any key in the course and rotate their own.

Only a hash of each key is stored, so a key is shown once, when it's made. Every request made with a key is logged (`sections.api_keys`) with the key, its owner, the function and who it ran as. After 10 failed key attempts in 15 minutes, a client is refused (HTTP 429) until the window passes. Clients are told apart by `X-Forwarded-For`, so behind a load balancer set `TRUSTED_PROXY_HOPS=1`; otherwise every request looks like it came from the load balancer, and 10 bad attempts from anyone lock out everyone. Example request:

```
curl -X POST \
  -H "Authorization: Bearer $SECTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "email": "<admin>@berkeley.edu",
        "args": {
            "email": "<student>@berkeley.edu"
        }
      }' \
  "https://<sections-host>/offerings/<canvas course id>/api/sudo/get_student_discussion_attendance"
```

`get_student_discussion_attendance` is only for admins, so `"email"` must name an admin, or be left out to run as the key's owner. Responses are `{"success": true, "data": ...}` on success. If the function itself fails (say, `"email"` names someone the function isn't allowed for, such as a non-admin here), the response is `{"success": false, "message": ...}` with HTTP 200. If the request is refused (a bad key, an `"email"` outside the course, a body that isn't JSON), it has the same shape with an HTTP error status. Check `success`, not only the status code.

## Notes
1. Use `yarn typecheck` (TypeScript) and `yarn lint` (ESLint); CI runs both.
2. `print` output from the backend shows up right away, with `yarn dev` or `python3 -m server.main`. (`yarn dev` sets `PYTHONUNBUFFERED=1`; without it, Python would hold the output back until the server stops, since it goes through a pipe.)
3. To try the staff, admin or student views, sign in as someone with that role: with the mock Canvas, pick them on `/dev_login/` (see [Mock Canvas](#mock-canvas)); with the sandbox, give your sandbox account the role in Canvas. Roles come from Canvas at each sign-in, so editing them in the local database doesn't last.
