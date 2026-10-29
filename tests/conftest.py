"""pytest fixtures, as in seating's tests/conftest.py, for tests written as
plain functions. The unittest classes use tests/unit/support.py, which builds
the app the same way."""

import pytest

from application import create_app
from models import db as sqlalchemy_db
from tests.unit.support import TEST_CONFIG


@pytest.fixture()
def app():
    app = create_app(TEST_CONFIG)
    with app.app_context():
        sqlalchemy_db.create_all()
        yield app
        sqlalchemy_db.session.remove()
        sqlalchemy_db.drop_all()
        sqlalchemy_db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()
