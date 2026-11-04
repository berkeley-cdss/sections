from server.application import create_app

# gunicorn serves server.main:app, and `flask --app server.main ...` (run from the
# repository root) runs commands against it.
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
