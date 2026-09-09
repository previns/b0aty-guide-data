"""Read-only inspection of extracted source states for milestone review."""
import json
import sys
from pathlib import Path

guide = json.loads((Path(__file__).resolve().parents[1] / "dist/guide.json").read_text(encoding="utf-8"))


def walk(record):
    yield record
    for branch in record.get("whenIn", []):
        yield from walk(branch)


for key in sys.argv[1:]:
    quest = guide["questHelpers"][key]
    print("\nQUEST", key, quest["var"])
    for value, root in quest["steps"].items():
        records = list(walk(root))
        print(value, " | ".join(dict.fromkeys(
            str(r.get("panel")) + ": " + r.get("text", "") for r in records)))
