"""End to end tests: the app on a local server, used through headless Chrome as people
use it, against the fake Canvas. The server, browser and seed data are shared with the
a11y audit, in tests/browser.py."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from server.models import db
from tests.a11y.utils import slugify
from tests.browser import live_site

SCREENSHOTS = Path("e2e-screenshots")


@pytest.fixture(scope="session")
def live():
    with live_site() as site:
        yield site


@pytest.fixture()
def site(live):
    """The browser and server, with a freshly seeded database and no one signed in."""
    live.reset()
    yield live


@pytest.fixture()
def database(site):
    """A function that opens the app's database, to set up or check what a test can't see."""
    @contextmanager
    def database():
        with site.app.app_context():
            try:
                yield db.session
            finally:
                db.session.remove()
    return database


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    site = item.funcargs.get("site") if hasattr(item, "funcargs") else None
    if report.when == "call" and report.failed and site is not None:
        SCREENSHOTS.mkdir(exist_ok=True)
        site.driver.save_screenshot(str(SCREENSHOTS / f"{slugify(item.name)}.png"))
