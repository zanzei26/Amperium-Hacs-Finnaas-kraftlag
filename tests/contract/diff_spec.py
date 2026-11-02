"""Print what differs between two copies of Amperium's API description (information only).

    python tests/contract/diff_spec.py tests/contract/swagger.json live-swagger.json

Lists endpoints and schemas that were added or removed, and fields that were added, removed or
changed type. The exit code is 1 when anything differs, 0 when the two are the same.
"""
from __future__ import annotations

import json
import sys


def describe(spec):
    """Endpoint -> parameter names, and schema -> {field: type}, in a form that is easy to compare."""
    endpoints = {
        f"{method.upper()} {path}": sorted(p["name"] for p in op.get("parameters", []))
        for path, methods in spec["paths"].items()
        for method, op in methods.items()
        if isinstance(op, dict)
    }
    schemas = {
        name: {
            field: (prop.get("$ref", "").rsplit("/", 1)[-1] or prop.get("type", "?"))
            + ("?" if prop.get("nullable") else "")
            for field, prop in schema.get("properties", {}).items()
        }
        for name, schema in spec["components"]["schemas"].items()
    }
    return endpoints, schemas


def main(old_path, new_path):
    old_endpoints, old_schemas = describe(json.load(open(old_path, encoding="utf-8")))
    new_endpoints, new_schemas = describe(json.load(open(new_path, encoding="utf-8")))
    lines = []
    for name in sorted(old_endpoints.keys() - new_endpoints.keys()):
        lines.append(f"endpoint removed: {name}")
    for name in sorted(new_endpoints.keys() - old_endpoints.keys()):
        lines.append(f"endpoint added:   {name}")
    for name in sorted(old_endpoints.keys() & new_endpoints.keys()):
        if old_endpoints[name] != new_endpoints[name]:
            lines.append(f"parameters changed: {name}: {old_endpoints[name]} -> {new_endpoints[name]}")
    for name in sorted(old_schemas.keys() - new_schemas.keys()):
        lines.append(f"schema removed: {name}")
    for name in sorted(new_schemas.keys() - old_schemas.keys()):
        lines.append(f"schema added:   {name}")
    for name in sorted(old_schemas.keys() & new_schemas.keys()):
        old, new = old_schemas[name], new_schemas[name]
        for field in sorted(old.keys() - new.keys()):
            lines.append(f"field removed: {name}.{field}")
        for field in sorted(new.keys() - old.keys()):
            lines.append(f"field added:   {name}.{field}")
        for field in sorted(old.keys() & new.keys()):
            if old[field] != new[field]:
                lines.append(f"field changed: {name}.{field}: {old[field]} -> {new[field]}")
    print("\n".join(lines) if lines else "The two descriptions are the same (as far as this compares).")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
