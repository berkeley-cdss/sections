# Sections 


## Local Development Set Up

Requires Python 3.14 and Node 20 (`mise install` picks both up from `mise.toml`).

1. Copy `.env.example` to `.env` and fill in the Canvas sandbox `CANVAS_CLIENT_ID` and `CANVAS_CLIENT_SECRET` (ask a maintainer). Never commit `.env`.
2. Create a virtual environment and install the server dependencies:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r server/requirements.txt
   ```
3. Install the frontend dependencies with `yarn install`.
4. Run both with `yarn run dev`, or separately: the backend with `python3 main.py` from `server/` (port 8000) and the frontend with `yarn start` (port 3000, proxies API calls to 8000).
5. Run the backend tests from the repository root with `python -m unittest discover -s server -p "test_*.py"`.

## Authentication

One deployment serves every bCourses course, with the same routes as seating. Users log in through Canvas OAuth (`/login/`, which returns to `/authorized/`), and `/offerings` lists their courses. Each course offering lives under `/offerings/<canvas course id>/`. Roles come from each Canvas enrollment at sign-in: Teachers and TAs are staff, and Teachers and Lead TAs are admins. Members of the `ADMIN_OVERRIDE_CANVAS_COURSE_ID` course are staff and admin everywhere. Someone added to a course after signing in needs to sign out and in again.

Course staff set up Sections for a course with "Import courses from canvas" (`/offerings/new`). Courses moved from the monorepo store their data under an old key (`cs61a`, `data8`, ...); link each one to its Canvas course with `flask --app main link-course <canvas id> <key> "<name>"`, run from `server/` against that database.

To sign in locally, click `Sign in`. You will be sent to `localhost:3000/login/`; change the port to 8000 (`localhost:8000/login/`) and finish signing in with Canvas, then go back to `localhost:3000`. The course list (`/offerings`) is only served by the backend, at `localhost:8000/offerings`. A "template not found" error on port 8000 after signing in is expected, because the built frontend isn't served in development.

### About the Sandbox

The production Sections app is deployed on GCP Cloud Run and interacts with bCourses. To locally mock this setup without exposing the production Canvas API keys, we use a "sandbox" Canvas instance located at [ucberkeleysandbox.instructure.com](https://ucberkeleysandbox.instructure.com/). During onboarding to the sections app, you will be added as an admin to the sandbox Canvas instance where you can view the development API key and create new API keys as needed.

**All development work should be done using the sandbox instance.** Access to bCourses should only be available in the production deployment once all testing with the sandbox is complete. You can do anything you'd like in the sandbox to simulate your desired testing environment (create courses, add students, specify user roles, etc.). You can make your own course, but we currently have a course  set up with users that can be found (after logging) by accessing the "Admin" button on the sidebar, then clicking "UC Berkeley Sandbox". Search through the courses for the one titled "Mango 101 (Deokpy Section)".

### More About Accessing Canvas APIs

Our wrapper for the Canvas API is `server/canvas_service.py`, which also lists the scopes the app requests at login. Those scopes must match the scopes on the app's Canvas developer key.

bCourses API keys have strict scope and permissions. bCourses API keys should only be used for the exact purpose they were granted for. Specifically, the sections app API key should not be used by another app or for any purpose outside the approved scope for the sections app. If you need a new API key with broader scope or for a different app, please contact @pancakereport to discuss. The process for obtaining a new API key requires faculty or full time staff (like @pancakereport) support and working with RTL who manage bCourses.

## Import Test Sections Locally

1. Start the server and front end.
2. Set up your sandbox course, either by signing in and using "Import courses from canvas" on `localhost:8000/offerings`, or with `python3 seed.py 157` from `server/` (157 is Mango 101 on the sandbox; this also adds demo sections).
3. From the `server` directory, import example sections and enrollment into that course:

```
python3 import_locally.py --course 157 --type sections --file test_csvs/test_sections.csv
python3 import_locally.py --course 157 --type enrollment --file test_csvs/disc_enrollment.csv
python3 import_locally.py --course 157 --type enrollment --file test_csvs/lab_enrollment.csv
```

4. Open `localhost:3000/offerings/157/`; you should see the example sections.

## Import Sections from GCP
1. Download the sections database to obtain a `.sql` file. Relevant Links [1](https://cloud.google.com/sql/docs/mysql/import-export/import-export-sql) and [2](https://cloud.google.com/storage/docs/downloading-objects).
2. Likely the export uses MySQL syntax, so update it to SQLite.
3. In the `server` directory, delete `app.db` and run `sqlite3 app.db < gcp-sections-export.sql`.

## API
Functions marked with the `@api` decorator are also exposed at `/api/sudo/<name>`, which runs the function as the user with the given email. These endpoints are disabled unless the `API_SECRET` environment variable is set, and every request must include that secret. Anyone with the secret can act as any user, so store it in Secret Manager and never commit it. Example request:

```
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
        "secret": "",
        "email": "", # the user to act as
        "args": {
            "email": "<student>@berkeley.edu"
        }
      }' \
  "https://<sections-host>/api/sudo/get_student_discussion_attendance"
```

## Notes
1. Use `yarn run flow` for typechecking.
2. If you'd to see debugging logs while the server is up and running, the usual `print` statements will not work. Instead, a method that currently works is described in this [commit](https://github.com/Cal-CS-61A-Staff/berkeley-cs61a/commit/0e75b8798543c0edd68cc02d1d9c1a9389105087).
3. If you run the app locally and sign in, you may need to update the local database to give yourself appropriate access levels to test the admin, staff, and student views. To assign yourself staff and admin access run the following (substituting your own email) *after* having already logged in:

    ```
    $ sqlite3 server/app.db
    $ sqlite> UPDATE user SET is_staff = 1, is_admin = 1 WHERE email = '<example>@berkeley.edu';
    $ sqlite> .exit
    ```
    If at any point you receive a error despite having mocked the proper permissions, you should clear your cookies at `localhost:3000` (Inspect page -> "Application" tab -> "Clear site data" button)
