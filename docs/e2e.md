# End to End Tests

`tests/e2e/` uses Sections in headless Chrome the way students and staff do: it clicks the real
pages, served by the app with the React build, and checks what changes on the page and in the database.
The `E2E` workflow runs these tests on each push and pull request.

## What they cover

| File | Flows |
|---|---|
| `test_student.py` | A student sees their section, joins a discussion, switches labs, leaves a lab, and needs a section's enrollment code to join it |
| `test_staff.py` | A TA starts a session and takes attendance, which the student then sees in their history. A teacher adds a student to a section's roster by email and removes another |
| `test_admin.py` | An admin sets the staff page link that everyone sees in the nav bar, and stops students joining discussions. Students can't open the admin page |
| `test_offerings.py` | A TA imports a course from Canvas. Signing out, then signing in from a course page, returns to that page |

Everyone signs in through `/dev_login/` against the [mock Canvas](developers.md#mock-canvas), as Oski Bear
(teacher), Yu Long (TA) or Jimmy Xu (student).

## How they work

The server, browser and seed data are in `tests/browser.py`, shared with the [a11y audit](a11y.md). One
server and one Chrome serve the whole run. Before each test, the `site` fixture (`tests/e2e/conftest.py`)
seeds a fresh database and signs out, so each test starts from the same course: a lab, a discussion and a
tutoring section run by the TA, with the student in the lab.

`site` has helpers for finding things the way a person does, by their visible text:
`site.visit(path, user)`, `site.click("Join Section", within)`, `site.card("Wheeler 150")`, and
`site.wait(condition)`. The `database` fixture opens the app's database, to set up what a test needs or
check what the page did.

**After an action, wait for its result.** The course pages are React, so a click's API call may only
start after the click returns, and the page updates after the response arrives. Wait for what the action
should do (`site.wait(lambda: sections_of(database) == [...])`, or for text to appear) instead of checking
right away. Checking right away passes or fails depending on timing.

## Running them

They need the frontend build in `server/static/` and Chrome, as the a11y audit does:

```bash
yarn build && cp -R build/. server/static/
pytest tests/e2e
```

Rebuild after changing the frontend. A failing test saves a screenshot of the page in `e2e-screenshots/`.
In CI these are uploaded as the `e2e-screenshots` artifact of a failed run.

## Adding a test

Add a test for a flow people depend on, in the file for whose flow it is, or a new `test_<subject>.py`.
Use the seeded course where you can, and add what a test needs with `database`, as
`test_student_switches_to_another_lab` does. Unit tests (`tests/unit/`) are faster and the better place
for the server's rules and edge cases. The end to end tests check that the pages and the server work
together.
