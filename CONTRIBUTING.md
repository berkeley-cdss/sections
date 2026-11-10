# Contributing

Thank you for your interest in contributing to Sections.

## How to Contribute

You can propose changes to Sections by:

1. **Forking** this repository
   See GitHub's guide on forking:
   https://help.github.com/articles/fork-a-repo/
   It is also perfectly acceptable to work on a **branch** if you have write access to this repository.
   Reach out to maintainers if you'd like write access.

2. **Making edits** in your fork or branch
   See [Developing Sections](docs/developers.md) to set up the app locally. Examples of useful contributions include:
   - Fixing typos and broken features.
   - Implementing new features that will be useful for **all courses** using Sections. If you're unsure whether a feature fits, please open an [issue](https://github.com/berkeley-cdss/sections/issues) to start a discussion.
   - Anything that addresses an [open issue](https://github.com/berkeley-cdss/sections/issues).
   - Improved documentation that accounts for personal experience developing or using Sections.

3. **Submitting a Pull Request**
   Learn more about pull requests here:
   https://help.github.com/articles/about-pull-requests/

   Please include:
   - A clear description of what you changed
   - The motivation for the change, and the issue it closes, if any (`Closes #123`)
   - Any relevant context or screenshots

   Ensure that your pull request also includes documentation for your changes. Documentation lives in the `docs` directory and is intended for people developing Sections.

## Contribution Guidelines

- Aim for **singular, focused updates.** If your contribution spans multiple features, consider submitting separate PRs. For complex overhauls that can't be easily split, please keep maintainers in the loop to ensure a smooth merge.
- Follow the existing **style and structure** of the code and docs.
- Use **inclusive language**, both in your documentation and code.
- Add or update tests for what you change, and run them locally (see [Testing](docs/testing.md)). CI runs the unit tests, the [end to end tests](docs/e2e.md), the [accessibility audit](docs/a11y.md), `flake8`, `yarn typecheck` and `yarn lint`, and they should all pass.
- If you change the database schema, commit the migration with the model change (see [Database Migrations](docs/migrations.md)). A PR with a migration can't be tried on its preview.
- If your change needs a new Canvas API scope, read [Canvas API Keys](README.md#canvas-api-keys) before starting: the production key's scopes need approval from bCourses.
