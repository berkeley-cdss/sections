"""The server's cache of Cal 1 Card photos (c1c_service.py), as in seating's server/cache.py."""

from flask_caching import Cache

# Set up for each app by create_app, from the CACHE_ settings in config.py.
cache_store = Cache()


# Input: sid, a student's ID number.
# Output: the key their photo is saved under in cache_store.
# Description: The same key seating uses.
def cache_key_photo(sid: str) -> str:
    return f"student_photo_{sid}"
