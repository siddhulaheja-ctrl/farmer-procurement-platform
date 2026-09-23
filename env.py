"""Loads .env into os.environ (setting env vars differs between powershell,
cmd and bash and we kept getting it wrong). Real env vars win."""

import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_loaded = False


def load():
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
            # FOO=bar  # comment
            hashed = value.find(" #")
            if hashed != -1:
                value = value[:hashed].strip()
            value = value.strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
