import os

from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

from config import load_config
from courses import create_course_list
from login import create_login_client
from models import db
from state import create_state_client

app = Flask(
    __name__, static_url_path="", static_folder="static", template_folder="static"
)
app.url_map.strict_slashes = False
# Course pages are the React build in static/; server-rendered pages live in templates/.
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")),
])
# Cloud Run terminates TLS, so trust its X-Forwarded-Proto for external URLs.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

load_config(app)
db.init_app(app)
create_state_client(app)
create_login_client(app)
create_course_list(app)


@app.route("/health")
def health():
    return "ok"


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
