# Developing Sections

## Local Development Set Up

Requires Python 3.14 and Node 24 (`mise install` picks both up from `mise.toml`), and Chrome for the browser tests. The frontend is React 19 and TypeScript, built with Vite.

The commands below are for macOS and Linux. On Windows, use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and run them in its Linux shell.

1. Copy `.env.example` to `.env`. Never commit `.env`. By default the app mocks Canvas, so no Canvas credentials are needed (see [Mock Canvas](#mock-canvas)); to use the [Canvas sandbox](#canvas-sandbox) instead, set `MOCK_CANVAS=false` and fill in its `CANVAS_CLIENT_ID` and `CANVAS_CLIENT_SECRET` (ask a maintainer).
2. Create a virtual environment and install the server dependencies:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r server/requirements.txt
   ```
3. Install the frontend dependencies with `yarn install`.
4. Create or update the local database with `flask --app server.main db upgrade` from the repository root. `server/` is a package, so run the app's commands from the root, as below.
5. Start the backend and the frontend together with `yarn dev`, or separately: the backend with `python3 -m server.main` (port 8000) and the frontend with `yarn start` (the Vite dev server on port 3000, which forwards API calls, the login routes and `/offerings` to port 8000).
6. Install the development dependencies (pytest, flake8, pip-audit, selenium) with `pip install -r requirements-dev.txt`, then run the backend tests with `pytest` from the repository root (see [Testing](testing.md)).
7. Optionally, check the frontend with `yarn typecheck` (TypeScript) and `yarn lint` (ESLint); CI runs both.

## Authentication

One deployment serves every bCourses course, with the same routes as seating. Users log in through Canvas OAuth (`/login/`, which returns to `/authorized/`), and `/offerings` lists their courses. Each course offering lives under `/offerings/<canvas course id>/`. Roles come from each Canvas enrollment at sign-in: Teachers and TAs are staff, and Teachers and Lead TAs are admins. Members of the `ADMIN_OVERRIDE_CANVAS_COURSE_ID` course are staff and admin everywhere. Someone added to a course after signing in needs to sign out and in again.

Course staff set up Sections for a course with "Import courses from Canvas" (`/offerings/new`). Offerings moved from the monorepo store their data under an old key (`cs61a`, `data8`, ...) and have been already linked to their Canvas courses. If one ever needs relinking, run `flask --app server.main link-offering <canvas id> <key> "<name>"`, run from the repository root against that database.

Locally, Canvas is either mocked (the default) or the Canvas sandbox (`MOCK_CANVAS=false`). Mocking is easiest for most work. If you are making changes that require a change to the Canvas key, you should ensure the changes work locally using the Canvas sandbox before requesting a change to the production key (see [Canvas API Keys](../README.md#canvas-api-keys)).

### Mock Canvas

Development mocks Canvas unless `MOCK_CANVAS=false`, so a fresh checkout can be signed into without any Canvas credentials, and tests can sign in without reaching Canvas. Logging in goes to `/dev_login/`, which lists the mock Canvas's users and their roles in each course; pick one to sign in as them. To try the staff, admin or student views, sign in as a user with that role. The users, courses and enrollments are in `server/fake_canvas_data/`, and `server/fake_canvas.py` answers the Canvas calls in `server/canvas_service.py` from them. Staff can import those courses with "Import courses from Canvas" and add their students by email as usual. Staging and production never mock Canvas, whatever `MOCK_CANVAS` says, and `/dev_login/` redirects home whenever Canvas isn't mocked.

To fill a course with sections, see [Sample Sections](#sample-sections).

### Canvas Sandbox

The production Sections app is deployed on GCP Cloud Run and talks to bCourses, UC Berkeley's Canvas. The Canvas sandbox, [ucberkeleysandbox.instructure.com](https://ucberkeleysandbox.instructure.com/), is a separate, real Canvas instance for testing, with its own developer keys, so local development never needs the production bCourses key. Talk to maintainers to be added to the Canvas sandbox. You'll be an admin there, so you can view/edit the development key and create new keys as needed.

You can do anything you'd like in the sandbox to simulate your desired testing environment (create courses, add students, specify user roles, etc.). To try the staff, admin or student views, give your sandbox account that role in a course. You can make your own course, but we currently have a course set up with users, which you can find (after signing in) by clicking the "Admin" button on the sidebar, then "UC Berkeley Sandbox". Search through the courses for the one titled "Mango 101 (Deokpy Section)".

To sign in locally against the sandbox, open `localhost:3000/offerings` and log in. This works on port 3000 if the sandbox developer key allows `http://localhost:3000/authorized/` as a redirect URI. Otherwise, log in at `localhost:8000/login/` instead, then go back to `localhost:3000`. A "template not found" error for course pages on port 8000 is expected: in development, the course pages are served by the Vite dev server on port 3000, not by the backend.

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

Use "Mango 101 (Deokpy Section)" (Canvas course `157` on the sandbox), with `MOCK_CANVAS=false`. Your sandbox account needs a role in that course to open it. Once you've been added to the sandbox, you should be able to grant yourself this role.

1. Set up the course: sign in and use "Import courses from Canvas" on `localhost:3000/offerings`, or run `python3 -m server.seed 157`.
2. Optionally, import the example CSVs, as above with `--course 157`.
3. Open `localhost:3000/offerings/157/`; you should see the sections.
