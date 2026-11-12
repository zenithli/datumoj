#!/usr/bin/env python3
"""Strict offline, synthetic-only static builder. Python standard library only."""
import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path

MAX_BYTES = 65536
MAX_COUNT = 9007199254740991
ASSETS = ("index.html", "styles.css", "app.js", "model.js", "poller.js", "welcome.css", "welcome.js", "welcome-scene.svg")
KEYS = {
    "receipt": {"schema_version", "data_mode", "generated_at", "nas"},
    "nas": {"last_attempt", "inventory_check", "content_check", "restore_check"},
    "last_attempt": {"observed_at", "started_at", "completed_at", "result", "error_count"},
    "inventory_check": {"observed_at", "scope", "checked_objects", "missing_objects", "size_mismatches"},
    "content_check": {"observed_at", "scope", "checked_objects", "hash_mismatches"},
    "restore_check": {"observed_at", "scope", "result", "checked_objects"},
}
TIME_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class BuildError(Exception):
    """Only fixed codes may cross the CLI boundary."""


def fail(code):
    raise BuildError(code)


def exact_object(value, category):
    if type(value) is not dict:
        fail("E_OBJECT")
    if set(value) != KEYS[category]:
        fail("E_FIELDS")


def timestamp(value, nullable=True):
    if value is None and nullable:
        return None
    if type(value) is not str or not TIME_PATTERN.fullmatch(value):
        fail("E_TIME")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        fail("E_TIME")


def count(value):
    if value is not None and (type(value) is not int or not 0 <= value <= MAX_COUNT):
        fail("E_COUNT")


def enumeration(value, choices):
    if type(value) is not str or value not in choices:
        fail("E_ENUM")


def validate_receipt(value):
    exact_object(value, "receipt")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        fail("E_SCHEMA")
    if value["data_mode"] != "synthetic":
        fail("E_MODE")
    generated = timestamp(value["generated_at"], nullable=False)
    exact_object(value["nas"], "nas")
    for key in KEYS["nas"]:
        item = value["nas"][key]
        exact_object(item, key)
        observed = timestamp(item["observed_at"])
        if observed is not None and observed > generated:
            fail("E_RELATION")
    job = value["nas"]["last_attempt"]
    enumeration(job["result"], {"unknown", "running", "success", "failed"})
    count(job["error_count"])
    start = timestamp(job["started_at"])
    completed = timestamp(job["completed_at"])
    observed = timestamp(job["observed_at"])
    if ((start is not None and start > generated)
            or (completed is not None and completed > generated)
            or (start is not None and completed is not None and start > completed)
            or (observed is not None and completed is not None and observed < completed)):
        fail("E_RELATION")
    inventory = value["nas"]["inventory_check"]
    enumeration(inventory["scope"], {"unknown", "reported_snapshot"})
    content = value["nas"]["content_check"]
    enumeration(content["scope"], {"unknown", "sample", "all_in_snapshot"})
    restore = value["nas"]["restore_check"]
    enumeration(restore["scope"], {"unknown", "sample"})
    enumeration(restore["result"], {"unknown", "passed", "failed"})
    for item, fields in (
        (inventory, ("checked_objects", "missing_objects", "size_mismatches")),
        (content, ("checked_objects", "hash_mismatches")),
        (restore, ("checked_objects",)),
    ):
        for field in fields:
            count(item[field])
        checked = item["checked_objects"]
        if checked is not None and any(item[field] is not None and item[field] > checked for field in fields[1:]):
            fail("E_RELATION")
    return value


def reject_constant(_value):
    fail("E_JSON")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("E_DUPLICATE_KEY")
        result[key] = value
    return result


def no_symlinks(path):
    # Preserve .. until after inspection: abspath/resolve would erase links.
    absolute = Path(path)
    if not absolute.is_absolute():
        absolute = Path.cwd() / absolute
    # Inspect root to leaf, refusing a link before traversing it or its .. child.
    for part in reversed((absolute, *absolute.parents)):
        if part.is_symlink():
            fail("E_SYMLINK")
    return absolute


def read_receipt(path):
    path = no_symlinks(path)
    # O_NOFOLLOW additionally refuses a final-component replacement by a symlink.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            fail("E_INPUT_TYPE")
        if info.st_size > MAX_BYTES:
            fail("E_INPUT_SIZE")
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        fail("E_INPUT_SIZE")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        fail("E_JSON")
    return validate_receipt(value)


def build(input_path, output_path):
    output = no_symlinks(output_path)
    if output.exists():
        fail("E_OUTPUT_EXISTS")
    if not output.parent.is_dir():
        fail("E_OUTPUT_PARENT")
    value = read_receipt(input_path)
    source_dir = Path(__file__).resolve().parent.parent / "web"
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=".synthetic-build-", dir=output.parent))
        for name in ASSETS:
            asset = no_symlinks(source_dir / name)
            if not asset.is_file():
                fail("E_ASSET")
            shutil.copyfile(asset, staging / name)
        (staging / "status.json").write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        # No publication until every fixed asset and the validated JSON are ready.
        no_symlinks(output)
        if output.exists():
            fail("E_OUTPUT_EXISTS")
        staging.rename(output)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        fail("E_ARGS")


def main(argv=None):
    parser = SafeParser(description="Build a synthetic-only offline NAS dashboard.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("synthetic",), default="synthetic")
    try:
        args = parser.parse_args(argv)
        build(args.input, args.output)
    except BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, RecursionError):
        print("E_IO", file=sys.stderr)
        return 1
    print("BUILD_OK_SYNTHETIC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
