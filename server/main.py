from application import create_app

# gunicorn serves main:app, and `flask --app main ...` runs commands against it.
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
