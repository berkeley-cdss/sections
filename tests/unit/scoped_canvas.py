"""Canvas's API as a token from a developer key with enforced scopes sees it,
for testing the requests canvas_service makes through canvasapi.

It follows Canvas's source (github.com/instructure/canvas-lms) where that
decides whether a request is refused:

- A request is allowed if its path matches one of the token's scopes
  (AccessToken#url_scopes_for_method, AuthenticationMethods#validate_scopes).
  That includes the links to a list's later pages, which canvasapi follows.
- Those links go to the route the controller names when it paginates, which
  isn't always the route requested: courses/:course_id/search_users links to
  courses/:course_id/users (CoursesController#users).
- Without "Allow include parameters" on the key, ``include[]`` is dropped.
"""

import json
import re
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode, urlparse

import requests

MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 10

# Each route canvas_service may request, and for a list, the route Canvas links
# its other pages to (the `Api.paginate` call in the route's controller action).
ROUTES = {
    "users/:id": None,
    "users/:user_id/profile": None,
    "users/:user_id/courses": "users/:user_id/courses",
    "courses/:id": None,
    "courses/:course_id/enrollments": "courses/:course_id/enrollments",
    "courses/:course_id/users": "courses/:course_id/users",
    "courses/:course_id/search_users": "courses/:course_id/users",
}


def scope_pattern(path: str) -> re.Pattern:
    """A scope's or route's path as the regexp Canvas matches request paths
    against: ``:name`` segments match anything but a slash."""
    return re.compile("^" + re.sub(r":[^/)]+", "[^/]+", path) + r"(?:\.[^/]+|)$")


def person(canvas_id, type="student", state="active", role=None, email=..., **fields):
    """Someone's enrollment in a course. ``type`` is as the users endpoints
    name it ("student", "ta", "teacher"); no ``email`` means Canvas shares none."""
    return {"id": canvas_id, "name": f"Person {canvas_id}", "short_name": f"P{canvas_id}",
            "login_id": str(1000000 + canvas_id),
            "email": f"p{canvas_id}@test" if email is ... else email,
            "type": type, "state": state, "role": role or type.capitalize() + "Enrollment", **fields}


class ScopedCanvas:
    """``people`` is each course's enrollments (see ``person``) by course id,
    and ``user_courses`` each user's courses, as Canvas lists them, by user id."""

    def __init__(self, scopes, *, people=None, user_courses=None, allow_includes=True):
        self.scopes = list(scopes)
        self.people = people or {}
        self.user_courses = user_courses or {}
        self.allow_includes = allow_includes
        # The path of every request, in order, and of those refused for their scope.
        self.requested = []
        self.refused = []

    @contextmanager
    def answering_canvasapi(self):
        """Answer the GET requests canvasapi makes, instead of the network."""
        def get(session, url, headers=None, params=None, **kwargs):
            return self.get(url, params)

        with patch.object(requests.Session, "get", get):
            yield self

    def used_scopes(self) -> set:
        """The scopes that allowed at least one request."""
        return {scope for scope in self.scopes
                if any(self._scope_allows(scope, path) for path in self.requested if path not in self.refused)}

    @staticmethod
    def _scope_allows(scope, path) -> bool:
        method, scope_path = scope.removeprefix("url:").split("|")
        return method == "GET" and bool(scope_pattern(scope_path).match(path))

    def get(self, url, params=None) -> requests.Response:
        parsed = urlparse(url)
        # canvasapi keeps the slash that ends CANVAS_SERVER_URL; Canvas ignores it.
        path = re.sub(r"/+", "/", parsed.path)
        query = parse_qsl(parsed.query) + [(key, str(value)) for key, value in (params or [])]
        self.requested.append(path)
        if not any(self._scope_allows(scope, path) for scope in self.scopes):
            self.refused.append(path)
            return self._response(401, {"errors": [{"message": "Insufficient scopes on access token."}]})
        if not self.allow_includes:
            query = [(key, value) for key, value in query if key not in ("include[]", "includes[]")]

        for route, link_route in ROUTES.items():
            if scope_pattern("/api/v1/" + route).match(path):
                break
        else:
            return self._response(404, {"errors": [{"message": "The specified resource does not exist."}]})
        ids = [int(part) for part in path.split("/") if part.isdigit()]
        answer = getattr(self, "_" + re.sub(r"\W+", "_", route.replace(":", "")))(ids[0], query)
        if link_route is None:
            return self._response(200, answer)
        link_path = "/api/v1/" + re.sub(r":\w+", str(ids[0]), link_route)
        return self._page(answer, query, f"{parsed.scheme}://{parsed.netloc}{link_path}")

    @staticmethod
    def _response(status, body, headers=None) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers.update(headers or {})
        return response

    def _page(self, items, query, link_url) -> requests.Response:
        asked = dict(query)
        page = int(asked.get("page", 1))
        per_page = min(int(asked.get("per_page", DEFAULT_PER_PAGE)), MAX_PER_PAGE)
        start = (page - 1) * per_page
        kept = [(key, value) for key, value in query if key not in ("page", "per_page")]

        def link(number, rel):
            return f'<{link_url}?{urlencode(kept + [("page", number), ("per_page", per_page)])}>; rel="{rel}"'

        links = [link(page, "current"), link(1, "first")]
        if start + per_page < len(items):
            links.append(link(page + 1, "next"))
        return self._response(200, items[start:start + per_page], {"Link": ",".join(links)})

    @staticmethod
    def _values(query, key) -> list:
        return [value for name, value in query if name == key]

    def _users_id(self, user_id, query):
        return {"id": user_id, "name": f"Person {user_id}"}

    def _users_user_id_profile(self, user_id, query):
        return {"id": user_id, "name": f"Person {user_id}", "short_name": f"P{user_id}",
                "primary_email": f"p{user_id}@test", "login_id": str(1000000 + user_id)}

    def _users_user_id_courses(self, user_id, query):
        states = self._values(query, "enrollment_state")
        include_term = "term" in self._values(query, "include[]")
        return [{key: value for key, value in course.items() if key != "term" or include_term}
                for course in self.user_courses.get(user_id, [])
                if not states or any(e["enrollment_state"] in states for e in course["enrollments"])]

    def _courses_id(self, course_id, query):
        return {"id": course_id, "name": f"Course {course_id}", "course_code": f"C{course_id}"}

    def _courses_course_id_enrollments(self, course_id, query):
        types = self._values(query, "type[]")
        states = self._values(query, "state[]") or ["active", "invited"]
        return [{"id": number, "type": p["type"].capitalize() + "Enrollment", "role": p["role"],
                 "enrollment_state": p["state"],
                 "user": {key: p[key] for key in ("id", "name", "short_name", "login_id")}}
                for number, p in enumerate(self.people.get(course_id, []), start=1)
                if (not types or p["type"].capitalize() + "Enrollment" in types) and p["state"] in states]

    def _courses_course_id_users(self, course_id, query):
        """Each person once, however many of their enrollments match. Canvas
        adds the email it shares whether or not ``include[]`` asks for it."""
        types = self._values(query, "enrollment_type[]")
        states = self._values(query, "enrollment_state[]") or ["active", "invited"]
        users = {}
        for p in self.people.get(course_id, []):
            if (not types or p["type"] in types) and p["state"] in states:
                users[p["id"]] = {key: p[key] for key in ("id", "name", "short_name", "login_id", "email")
                                  if p[key] is not None}
        return list(users.values())

    _courses_course_id_search_users = _courses_course_id_users
