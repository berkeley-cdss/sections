# Database Migrations

The schema is managed with Flask-Migrate (Alembic); migrations live in `server/migrations/versions`. To change the schema, edit `server/models.py`, then from the repository root:

```
flask --app server.main db migrate -m "describe the change"   # generates a migration; review and edit it
flask --app server.main db upgrade                             # applies it to your local database
```

Commit the migration with the model change. Deployments with `RUN_MIGRATIONS=true` (staging and production) run `flask db upgrade` when they start; PR previews never run migrations, because they share the staging database and we don't want to make the database unusable for staging.

## Migrations and PR Previews

Sections checks that the database's migration matches the code's latest migration (`server/schema_check.py`). While they differ, every page, API call and `/health` returns 503, rather than failing on the first query that uses a missing column. The check is repeated at most once a minute.

This means **a PR that adds a migration can't be tried on its preview.** The preview shares the staging database, which only gets the migration when the PR is merged and staging deploys, so the preview shows "This is a preview of PR #N, which adds a database migration… Merge the PR to see its changes on staging." Test such a PR locally (`flask --app server.main db upgrade` against your own database), then merge it and check staging.

The reverse also happens: after another PR with a migration is merged, staging's database is ahead of a preview whose branch doesn't have that migration. The preview then says to merge main into the PR's branch, which redeploys the preview with the migration.

Locally, the same check tells you to run `flask --app server.main db upgrade` when your database is behind, for example after pulling a new migration.
