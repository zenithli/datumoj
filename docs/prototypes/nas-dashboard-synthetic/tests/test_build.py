"""Black-box builder tests: fixed literal expectations, no production validator oracle."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build.py"
FIXTURE = json.loads((ROOT / "examples/synthetic-status.json").read_text())
ASSETS = {"index.html", "styles.css", "app.js", "model.js", "poller.js", "status.json", "welcome.css", "welcome.js", "welcome-scene.svg"}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "input.json"
        self.output = self.base / "output"

    def run_build(self, data=None, raw=None, output=None, extra=()):
        if raw is not None:
            self.source.write_bytes(raw)
        elif data is not None:
            self.source.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(BUILDER), "--input", str(self.source),
             "--output", str(output or self.output), "--mode", "synthetic", *extra],
            capture_output=True, text=True, check=False,
        )

    def assert_rejected(self, result, code):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), code)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["input.json"])

    def test_canonical_build_exact_allowlist_normalized_and_deterministic(self):
        result = self.run_build(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.strip(), "BUILD_OK_SYNTHETIC")
        self.assertEqual({p.name for p in self.output.iterdir()}, ASSETS)
        actual = (self.output / "status.json").read_bytes()
        self.assertEqual(json.loads(actual), FIXTURE)
        expected = (json.dumps(FIXTURE, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        self.assertEqual(actual, expected)
        other = self.base / "second"
        self.assertEqual(self.run_build(FIXTURE, output=other).returncode, 0)
        for name in ASSETS:
            self.assertEqual((self.output / name).read_bytes(), (other / name).read_bytes())
        for name in ASSETS - {"status.json"}:
            self.assertEqual((self.output / name).read_bytes(), (ROOT / "web" / name).read_bytes())
        self.assertEqual(json.loads((ROOT / "web/status.json").read_text()), FIXTURE)

    def test_welcome_svg_is_static_and_all_built_references_resolve(self):
        result = self.run_build(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name for p in self.output.iterdir()}, ASSETS)
        self.assertEqual(len(ASSETS), 9)
        svg_path = self.output / "welcome-scene.svg"
        self.assertTrue(svg_path.is_file(), "original local artwork must be built")
        svg = svg_path.read_text()
        self.assertNotIn("<!DOCTYPE", svg.upper())
        self.assertNotIn("<!ENTITY", svg.upper())
        root = ET.fromstring(svg)
        allowed = {"svg", "g", "rect", "path", "circle", "ellipse", "polygon", "polyline", "line", "title", "desc"}
        for element in root.iter():
            self.assertIn(element.tag.rsplit("}", 1)[-1], allowed)
            for key, value in element.attrib.items():
                name = key.rsplit("}", 1)[-1].lower()
                self.assertFalse(name.startswith("on"), "no SVG event handlers")
                self.assertNotIn(name, {"href", "src"}, "no SVG linked resources")
                self.assertNotIn("url(", value.lower(), "no SVG resource references")
                self.assertNotIn("javascript:", value.lower())

        class References(HTMLParser):
            def __init__(self):
                super().__init__()
                self.references = []
                self.ids = []

            def handle_starttag(self, _tag, attrs):
                attrs = dict(attrs)
                if "id" in attrs:
                    self.ids.append(attrs["id"])
                for key in ("href", "src"):
                    if key in attrs:
                        self.references.append(attrs[key])

        page = References()
        page.feed((self.output / "index.html").read_text())
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for reference in page.references:
            if reference.startswith("#"):
                self.assertIn(reference[1:], page.ids)
            else:
                self.assertNotIn(":", reference)
                self.assertNotIn("..", Path(reference).parts)
                self.assertFalse(Path(reference).is_absolute())
                self.assertTrue((self.output / reference).is_file(), "local reference must resolve")

    def test_invalid_objects_rejected_without_echo_or_partial_publish(self):
        cases = []

        def add(label, change, code):
            value = copy.deepcopy(FIXTURE)
            change(value)
            cases.append((label, value, code))

        add("nested extra", lambda r: r["nas"]["content_check"].update(secret="/fake/private/SECRET_VALUE"), "E_FIELDS")
        for name in ("__proto__", "constructor", "prototype"):
            add(name, lambda r, n=name: r["nas"]["restore_check"].update({n: "SECRET_VALUE"}), "E_FIELDS")
        add("mode", lambda r: r.update(data_mode="reported"), "E_MODE")
        add("schema bool", lambda r: r.update(schema_version=True), "E_SCHEMA")
        add("schema float", lambda r: r.update(schema_version=1.0), "E_SCHEMA")
        add("null generated", lambda r: r.update(generated_at=None), "E_TIME")
        for value in (True, 1.5, 1.0, -1, 9007199254740992):
            add(f"bad count {value!r}", lambda r, v=value: r["nas"]["content_check"].update(checked_objects=v), "E_COUNT")
        for value in ("2000-02-30T12:00:00Z", "1900-02-29T12:00:00Z", "0000-01-01T00:00:00Z", "2000-01-02T12:00:00.000Z", "2000-01-02T12:00:00+00:00"):
            add("bad time", lambda r, v=value: r.update(generated_at=v), "E_TIME")
        add("future observed", lambda r: r["nas"]["content_check"].update(observed_at="2000-01-03T00:00:00Z"), "E_RELATION")
        add("future start", lambda r: r["nas"]["last_attempt"].update(started_at="2000-01-03T00:00:00Z"), "E_RELATION")
        add("future completed", lambda r: r["nas"]["last_attempt"].update(completed_at="2000-01-03T00:00:00Z"), "E_RELATION")
        add("reversed job", lambda r: r["nas"]["last_attempt"].update(started_at="2000-01-02T11:51:00Z"), "E_RELATION")
        add("early observed", lambda r: r["nas"]["last_attempt"].update(observed_at="2000-01-02T11:49:00Z"), "E_RELATION")
        add("over checked", lambda r: r["nas"]["content_check"].update(hash_mismatches=13), "E_RELATION")
        add("inventory over checked", lambda r: r["nas"]["inventory_check"].update(missing_objects=121), "E_RELATION")
        add("bad enum", lambda r: r["nas"]["restore_check"].update(scope="all"), "E_ENUM")
        add("missing field", lambda r: r["nas"]["inventory_check"].pop("scope"), "E_FIELDS")
        cases += [("null", None, "E_OBJECT"), ("list", [], "E_OBJECT"), ("empty", {}, "E_FIELDS")]
        for label, data, code in cases:
            with self.subTest(label=label):
                self.assert_rejected(self.run_build(raw=json.dumps(data).encode()), code)

    def test_duplicates_and_nonfinite_json_are_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"nas":{"x":0,"x":1}}'):
            with self.subTest(raw=raw):
                self.assert_rejected(self.run_build(raw=raw), "E_DUPLICATE_KEY")
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.assert_rejected(self.run_build(raw=('{"x":' + value + '}').encode()), "E_JSON")
        self.assert_rejected(self.run_build(raw=b'{"broken":"SECRET_VALUE"'), "E_JSON")
        self.assert_rejected(self.run_build(raw=b'\xff'), "E_JSON")

    def test_oversized_input_and_wrong_cli_mode(self):
        self.assert_rejected(self.run_build(raw=b' ' * 65537), "E_INPUT_SIZE")
        self.assert_rejected(self.run_build(FIXTURE, extra=("--mode", "reported")), "E_ARGS")

    def test_existing_output_never_clobbered(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("preserve")
        result = self.run_build(FIXTURE)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_OUTPUT_EXISTS")
        self.assertEqual(marker.read_text(), "preserve")
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_symlink_input_and_output_refused(self):
        actual = self.base / "actual.json"
        actual.write_text(json.dumps(FIXTURE))
        self.source.symlink_to(actual)
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_SYMLINK")
        self.assertFalse(self.output.exists())
        self.source.unlink()
        self.source.write_text(json.dumps(FIXTURE))
        target = self.base / "target"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_SYMLINK")
        self.assertEqual(list(target.iterdir()), [])

    def test_symlink_parent_refused_and_missing_input_safe(self):
        target = self.base / "target"
        target.mkdir()
        link = self.base / "alias"
        link.symlink_to(target, target_is_directory=True)
        result = self.run_build(FIXTURE, output=link / "out")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_SYMLINK")
        self.assertEqual(list(target.iterdir()), [])
        self.source.unlink()
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_IO")

    def test_input_symlink_before_parent_segment_is_rejected(self):
        target = self.base / "other" / "nested"
        target.mkdir(parents=True)
        alias = self.base / "alias"
        alias.symlink_to(target, target_is_directory=True)
        self.source.write_text(json.dumps(FIXTURE))
        actual = copy.deepcopy(FIXTURE)
        actual["nas"]["inventory_check"]["checked_objects"] = 240
        (target.parent / "input.json").write_text(json.dumps(actual))
        argument = alias / ".." / "input.json"
        # The OS follows alias before .., unlike lexical abspath normalization.
        self.assertEqual(json.loads(argument.read_text()), actual)
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--input", str(argument),
             "--output", str(self.output)], capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_SYMLINK")
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.output.exists())
        self.assertEqual(json.loads(self.source.read_text()), FIXTURE)
        self.assertEqual(json.loads((target.parent / "input.json").read_text()), actual)
        self.assertFalse(list(self.base.glob(".synthetic-build-*")))

    def test_output_symlink_before_parent_segment_is_rejected(self):
        target = self.base / "other" / "nested"
        target.mkdir(parents=True)
        alias = self.base / "alias"
        alias.symlink_to(target, target_is_directory=True)
        argument = alias / ".." / "published"
        result = self.run_build(FIXTURE, output=argument)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_SYMLINK")
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.base / "published").exists())
        self.assertFalse((target.parent / "published").exists())
        self.assertFalse(list(self.base.glob(".synthetic-build-*")))
        self.assertFalse(list(target.parent.glob(".synthetic-build-*")))

    def test_ordinary_nonlink_parent_segments_preserve_os_path_behavior(self):
        plain = self.base / "plain"
        plain.mkdir()
        self.source.write_text(json.dumps(FIXTURE))
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--input", str(plain / ".." / "input.json"),
             "--output", str(plain / ".." / "output")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "BUILD_OK_SYNTHETIC")
        self.assertEqual(json.loads((self.output / "status.json").read_text()), FIXTURE)
        self.assertEqual({p.name for p in self.output.iterdir()}, ASSETS)
        self.assertEqual(list(plain.iterdir()), [])

    def test_missing_asset_after_staging_never_partially_publishes(self):
        clone = self.base / "isolated-builder"
        (clone / "tools").mkdir(parents=True)
        (clone / "web").mkdir()
        shutil.copyfile(BUILDER, clone / "tools/build.py")
        for name in ("index.html", "styles.css", "app.js", "model.js"):
            shutil.copyfile(ROOT / "web" / name, clone / "web" / name)
        self.source.write_text(json.dumps(FIXTURE))
        result = subprocess.run(
            [sys.executable, str(clone / "tools/build.py"), "--input", str(self.source),
             "--output", str(self.output)], capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "E_ASSET")
        self.assertFalse(self.output.exists())
        self.assertEqual({p.name for p in self.base.iterdir()}, {"isolated-builder", "input.json"})

    def test_max_safe_counts_nulls_and_leap_day_valid(self):
        r = copy.deepcopy(FIXTURE)
        r["generated_at"] = "2000-02-29T12:00:00Z"
        r["nas"]["content_check"]["checked_objects"] = 9007199254740991
        r["nas"]["last_attempt"]["started_at"] = None
        r["nas"]["last_attempt"]["error_count"] = None
        result = self.run_build(r)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.output / "status.json").read_text()), r)


if __name__ == "__main__":
    unittest.main()
