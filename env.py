"""Reads a .env file so we don't have to set environment variables by hand
every time we start the app. Setting them on the command line differs between
powershell, cmd and bash and we kept getting it wrong.

.env is gitignored, keys never go in the repo.

Anything already set in the real environment wins, so you can still override
one value for a single run.
"""

import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_loaded = False


def load():
    """Read .env into os.environ. Safe to call more than once."""
    global _loaded
    if _loaded or not os.path.exists(PATH):
        _loaded = True
        return
    _loaded = True
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # trailing comment, e.g. FOO=bar   # a note. only when there is a
            # space before the hash, so a value can still contain one
            hashed = value.find(" #")
            if hashed != -1:
                value = value[:hashed].strip()
            value = value.strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
