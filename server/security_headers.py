import flask

# Defense in depth should a script ever get injected: pages load scripts, styles, fonts and images
# only from this app, and fetch() only from this app, so an injected script cannot fetch() or load
# an image to hand data to another site. Neither the React build nor the server-rendered templates
# use inline <script> blocks or onclick= handlers, so script-src does not allow 'unsafe-inline';
# put any new script in a file instead.
# style-src does allow it: styled-components adds <style> tags at runtime.
# There is no form-action: browsers apply it to the redirects after a form is posted, and a post
# made once the Canvas token has expired is redirected to Canvas to log in again.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    # Bootstrap draws its checkboxes, selects and close buttons with data: SVGs
    "img-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
])


def add_security_headers(app: flask.Flask):
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
