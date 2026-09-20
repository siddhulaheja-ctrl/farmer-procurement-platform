"""Every string the portal translates, and which languages are missing it.

    python -m lang.check           # counts per language
    python -m lang.check hi        # the missing Hindi strings, one per line

Reads the literal calls to t() with a quoted string, in templates and python
files. A string built at run time, like t(place), is data and not listed here.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CALL = re.compile(r"""\b(?:t|_say)\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*[),|]""")
SKIP = {"lab", "graphify-out", "farmer-ivr", "docs", "models", "__pycache__", ".git", "venv", ".venv"}


def keys():
    found = {}
    for path in ROOT.rglob("*"):
        if path.suffix not in (".html", ".py") or SKIP & set(path.relative_to(ROOT).parts):
            continue
        source = path.read_text(encoding="utf-8")
        where = str(path.relative_to(ROOT))
        if path.suffix == ".py":
            # the parser joins "long " "strings" split over lines
            for n in ast.walk(ast.parse(source)):
                if (isinstance(n, ast.Call) and getattr(n.func, "id", None) in ("t", "_say") and n.args
                        and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                    found.setdefault(n.args[0].value, where)
            continue
        for m in CALL.finditer(source):
            text = (m.group(1) if m.group(1) is not None else m.group(2))
            text = text.replace('\\"', '"').replace("\\'", "'")
            found.setdefault(text, where)
    return found


def main():
    sys.path.insert(0, str(ROOT))
    from i18n import TABLES
    found = keys()
    want = sys.argv[1] if len(sys.argv) > 1 else None
    for code, table in TABLES.items():
        missing = sorted(k for k in found if k not in table)
        if want == code:
            for k in missing:
                print("%s\t%s" % (found[k], k))
        elif not want:
            print("%s: %d of %d strings missing" % (code, len(missing), len(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
