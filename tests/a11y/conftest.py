"""The a11y audit's site and its report of violations by rule. The server, browser
and seed data are shared with the end to end tests, in tests/browser.py."""

from collections import defaultdict

import pytest

from tests.a11y.utils import REPORT_DIR
from tests.browser import live_site, slugify

# rule id -> pages that break it, printed at the end of the run
VIOLATIONS_BY_RULE = defaultdict(set)


@pytest.fixture(scope="session")
def a11y_site():
    """One browser and server, shared by every page's a11y audit, which only looks."""
    with live_site() as site:
        yield site


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    site = item.funcargs.get("a11y_site") if hasattr(item, "funcargs") else None
    if report.when == "call" and report.failed and site is not None:
        screenshots = REPORT_DIR / "screenshots"
        screenshots.mkdir(parents=True, exist_ok=True)
        site.driver.save_screenshot(str(screenshots / f"{slugify(item.name)}.png"))


def pytest_terminal_summary(terminalreporter):
    if not VIOLATIONS_BY_RULE:
        return
    terminalreporter.section("accessibility violations by rule")
    for rule, pages in sorted(VIOLATIONS_BY_RULE.items()):
        terminalreporter.write_line(f"{rule} ({len(pages)} pages)")
        for page in sorted(pages):
            terminalreporter.write_line(f"  {page}")
