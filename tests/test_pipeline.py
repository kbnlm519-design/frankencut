import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import frankencut as fc


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "footage"
        self.source.mkdir()
        self.workspace = self.root / "generated"
        self.workspace.mkdir()
        self.video = self.source / "river-walk.mp4"
        self.video.write_bytes(b"original synthetic test fixture")
        self.asset = {"id": "asset-one", "path": str(self.video), "name": self.video.name,
                      "sha256": fc.digest(self.video), "duration": 4., "width": 640,
                      "height": 360, "duplicate_of": None, "thumbnails": []}
        self.library = {"root": str(self.source), "assets": [self.asset], "errors": []}

    def plan(self):
        with patch.object(fc, "preview", return_value=["begin", "middle", "end"]):
            return fc.make_plan(self.library, [{"query": "river", "start": .5, "seconds": 2}], self.workspace)

    def approved(self):
        result = self.plan()
        result["shots"][0]["text_review"] = "pass"
        return result

    def test_plan_uses_exact_interval_and_pending_review(self):
        plan = self.plan()
        self.assertEqual(plan["shots"][0]["start"], .5)
        self.assertEqual(plan["shots"][0]["seconds"], 2)
        self.assertEqual(plan["shots"][0]["text_review"], "pending")
        self.assertEqual(fc.load(self.workspace / "plan.json"), plan)

    def test_unmatched_request_never_substitutes_another_clip(self):
        with self.assertRaisesRegex(ValueError, "No unused footage matches"):
            fc.make_plan(self.library, [{"query": "city"}], self.workspace)

    def test_duplicate_and_already_used_asset_are_excluded(self):
        duplicate = dict(self.asset, id="asset-two", name="river-copy.mp4", duplicate_of=self.asset["name"])
        self.library["assets"].append(duplicate)
        with patch.object(fc, "preview", return_value=[]):
            with self.assertRaisesRegex(ValueError, "No unused footage matches"):
                fc.make_plan(self.library, [{"query": "river"}, {"query": "river"}], self.workspace)

    def test_export_requires_both_explicit_approval_and_review(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "Explicit export approval"):
            fc.render(plan, self.library, self.workspace)
        with self.assertRaisesRegex(ValueError, "Review all three"):
            fc.render(plan, self.library, self.workspace, approved=True)

    def test_modified_source_is_rejected(self):
        plan = self.approved()
        self.video.write_bytes(b"changed test footage")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            fc.validate_plan(plan, self.library, self.workspace)

    def test_changed_interval_needs_new_previews(self):
        plan = self.approved()
        plan["shots"][0]["start"] = 1.
        with self.assertRaisesRegex(ValueError, "Interval changed"):
            fc.validate_plan(plan, self.library, self.workspace)

    def test_hash_and_absolute_path_bans_are_checked(self):
        plan = self.approved()
        for entry in ({"source_sha": self.asset["sha256"]}, {"path": str(self.video)}):
            fc.save(self.workspace / "bans.json", {"entries": [entry]})
            with self.assertRaisesRegex(ValueError, "ban list"):
                fc.validate_plan(plan, self.library, self.workspace)

    def test_shared_ancestor_ban_list_is_checked(self):
        plan = self.approved()
        fc.save(self.source / "素材禁用清单.json", [{"source_sha": self.asset["sha256"]}])
        with self.assertRaisesRegex(ValueError, "ban list"):
            fc.validate_plan(plan, self.library, self.workspace)

    def test_source_cannot_be_swapped_for_external_path(self):
        plan = self.approved()
        external = self.root / "outside.mp4"
        external.write_bytes(self.video.read_bytes())
        self.library["assets"][0]["path"] = str(external)
        with self.assertRaisesRegex(ValueError, "outside the scanned"):
            fc.validate_plan(plan, self.library, self.workspace)

    def test_nonfinite_boolean_negative_and_long_intervals_are_rejected(self):
        for bad in (float("nan"), float("inf"), True, -1, "2"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                fc.number(bad, "Seconds", .2)
        with self.assertRaisesRegex(ValueError, "exceeds source"):
            fc.make_plan(self.library, [{"query": "river", "start": 3, "seconds": 2}], self.workspace)

    def test_scanner_excludes_generated_and_symlinked_folders(self):
        generated = self.source / "样片输出"
        generated.mkdir()
        (generated / "recycled.mp4").write_bytes(b"generated")
        external = self.root / "external"
        external.mkdir()
        (external / "other.mp4").write_bytes(b"external")
        (self.source / "linked").symlink_to(external, target_is_directory=True)
        probe = json.dumps({"format": {"duration": "4"}, "streams": [
            {"codec_type": "video", "width": 640, "height": 360}]})
        with patch.object(fc, "run", return_value=probe), patch.object(fc, "preview", return_value=[]):
            result = fc.scan(self.source, self.workspace)
        self.assertEqual([a["name"] for a in result["assets"]], ["river-walk.mp4"])
        self.assertEqual(self.video.read_bytes(), b"original synthetic test fixture")

    def test_tk_sources_require_dedicated_output_root(self):
        raw = self.root / "TK原素材" / "city"
        raw.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "For TK footage"):
            fc.scan(raw, self.workspace)
        outputs = raw.parent / "样片输出"
        outputs.mkdir()
        with self.assertRaisesRegex(ValueError, "cannot be indexed"):
            fc.scan(outputs, self.workspace)

    def test_render_validation_uses_one_saved_plan_snapshot(self):
        second_path = self.source / "mountain.mp4"
        second_path.write_bytes(b"second original synthetic fixture")
        self.library["assets"].append(dict(self.asset, id="asset-two", path=str(second_path),
                                           name="mountain.mp4", sha256=fc.digest(second_path)))
        with patch.object(fc, "preview", return_value=[]):
            plan = fc.make_plan(self.library, [{"query": "river"}, {"query": "mountain"}], self.workspace)
        for shot in plan["shots"]:
            shot["text_review"] = "pass"
        with patch.object(fc, "load", wraps=fc.load) as reader:
            fc.validate_plan(plan, self.library, self.workspace)
        reads = [call for call in reader.call_args_list if Path(call.args[0]).name == "plan.json"]
        self.assertEqual(len(reads), 1)

    def test_nested_custom_workspace_is_excluded_from_ingestion(self):
        nested = self.source / "custom-generated-data"
        nested.mkdir()
        (nested / "recycled.mp4").write_bytes(b"generated output")
        probe = json.dumps({"format": {"duration": "4"}, "streams": [
            {"codec_type": "video", "width": 640, "height": 360}]})
        with patch.object(fc, "run", return_value=probe), patch.object(fc, "preview", return_value=[]):
            library = fc.scan(self.source, nested)
        self.assertEqual([a["name"] for a in library["assets"]], ["river-walk.mp4"])


if __name__ == "__main__":
    unittest.main()
