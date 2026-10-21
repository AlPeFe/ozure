"""Tests run against the simulated body, so no camera is required."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ozure import cli
from ozure.catalog import load_catalog, repo_catalog_dir
from ozure.errors import InvalidRecipe
from ozure.fuji import FujiPtp
from ozure.mockcam import MockCameraTransport, props_from_recipe, state_from_recipes
from ozure.recipe import Recipe, dial, ptp_name, ptp_name_bytes, recipe_from_props

REPO = Path(__file__).resolve().parent.parent


def sample_recipe(**overrides) -> Recipe:
    data = {
        "name": "Test Recipe",
        "film_simulation": "classic_chrome",
        "dynamic_range": "dr200",
        "grain_effect": "weak_small",
        "color_chrome": "weak",
        "color_chrome_fx_blue": "strong",
        "smooth_skin": "off",
        "white_balance": {"mode": "daylight", "shift_r": -2, "shift_b": 3},
        "highlight": -1.0,
        "shadow": 1.5,
        "color": -2.0,
        "sharpness": 0.5,
        "noise_reduction": -2,
        "clarity": 1.0,
    }
    data.update(overrides)
    return Recipe.from_dict(data)


def camera(recipes: list[Recipe] | None = None) -> tuple[FujiPtp, MockCameraTransport]:
    recipes = recipes or [sample_recipe(name=f"C{i + 1}") for i in range(7)]
    transport = MockCameraTransport(state_from_recipes("X100VI", recipes))
    fuji = FujiPtp(transport)
    fuji.open()
    return fuji, transport


class WireFormatTests(unittest.TestCase):
    def test_ptp_string_round_trip(self):
        for name in ["", "A", "Acros Night", "ñandú ☕"]:
            self.assertEqual(ptp_name(ptp_name_bytes(name)), name)

    def test_ptp_string_rejects_junk(self):
        with self.assertRaises(InvalidRecipe):
            ptp_name(b"\x05\x41\x00")

    def test_property_block_round_trip(self):
        recipe = sample_recipe()
        decoded = recipe_from_props(recipe.name, props_from_recipe(recipe))
        self.assertEqual(decoded.to_dict(), recipe.to_dict())

    def test_empty_slot_is_representable(self):
        recipe = recipe_from_props("", [0xFFFF] * 19)
        self.assertTrue(recipe.empty)
        self.assertEqual(recipe.name, "")

    def test_grain_off_accepts_camera_normalised_value(self):
        recipe = sample_recipe(grain_effect="off")
        props = props_from_recipe(recipe)
        props[5] = 7  # what an X100VI stores for Off
        self.assertEqual(recipe_from_props("x", props).grain_effect, "off")

    def test_dial_rounding(self):
        self.assertEqual(dial(0.5), 5)
        self.assertEqual(dial(-1.25), -13)

    def test_alias_normalisation(self):
        recipe = Recipe.from_dict({"film_simulation": "Classic Negative", "white_balance": "AWB"})
        self.assertEqual(recipe.film_simulation, "classic_negative")
        self.assertEqual(recipe.white_balance.mode, "auto")

    def test_rejects_impossible_values(self):
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"white_balance": {"mode": "auto", "shift_r": 12}})
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"noise_reduction": 9})
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"film_simulation": "kodachrome"})


class CameraTests(unittest.TestCase):
    def test_reads_seven_slots(self):
        fuji, _transport = camera()
        profile = fuji.read_profile()
        self.assertEqual(len(profile), 7)
        self.assertEqual(profile[0].name, "C1")
        fuji.close()

    def test_write_then_read_round_trip(self):
        fuji, _transport = camera()
        recipe = sample_recipe(name="New Name")
        fuji.write_recipe(3, recipe)
        self.assertEqual(fuji.read_slot(3).to_dict(), recipe.to_dict())
        fuji.close()

    def test_monochrome_slot_keeps_colour_controls(self):
        fuji, transport = camera()
        mono = sample_recipe(name="Mono", film_simulation="acros")
        fuji.write_recipe(4, mono)
        written = {prop for prop, _ in transport.sent_props}
        # color chrome (0xD196) and fx blue (0xD197) must not be sent
        self.assertNotIn(0xD196, written)
        self.assertNotIn(0xD197, written)
        fuji.close()

    def test_identity_is_reported(self):
        fuji, _transport = camera()
        self.assertEqual(fuji.camera["model"], "X100VI")
        fuji.close()

    def test_write_recipe_can_keep_the_slot_name(self):
        fuji, _transport = camera()
        fuji.write_recipe(2, sample_recipe(name="ignored"), write_name=False)
        self.assertEqual(fuji.read_slot(2).name, "C2")
        fuji.close()


class CatalogTests(unittest.TestCase):
    def test_bundled_catalog_loads_and_validates(self):
        catalog = load_catalog(repo_catalog_dir())
        self.assertGreaterEqual(len(catalog), 5)
        for entry in catalog:
            self.assertTrue(entry.slug)
            self.assertTrue(entry.name)
            entry.recipe.validate()

    def test_bad_catalog_file_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(
                json.dumps({"name": "x", "recipe": {"film_simulation": "nope"}}), encoding="utf-8"
            )
            with self.assertRaises(InvalidRecipe):
                load_catalog(Path(tmp))


class CliTests(unittest.TestCase):
    """End-to-end through `main()`, which is what the skill actually calls."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = {"OZURE_HOME": str(self.home), "OZURE_MOCK": "1", "NO_COLOR": "1"}
        self._old_env = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, dict | None]:
        code = cli.main(list(args))
        return code, None

    def test_connect_seeds_the_simulator(self):
        self.assertEqual(cli.main(["connect", "--mock", "--json"]), 0)
        self.assertTrue((self.home / "mock-camera.json").exists())

    def test_write_requires_yes(self):
        cli.main(["connect", "--mock", "--json"])
        self.assertEqual(cli.main(["set", "C1", "--field", "shadow=1", "--mock", "--json"]), 10)
        self.assertEqual(
            cli.main(["set", "C1", "--field", "shadow=1", "--yes", "--mock", "--json"]), 0
        )

    def test_field_accepts_a_json_white_balance(self):
        cli.main(["connect", "--mock", "--json"])
        code = cli.main(
            [
                "set",
                "C3",
                "--field",
                'white_balance={"mode":"shade","shift_r":1,"shift_b":-2}',
                "--yes",
                "--no-backup",
                "--mock",
                "--json",
            ]
        )
        self.assertEqual(code, 0)
        state = json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))
        props = state["slots"][2]["props"]
        self.assertEqual(props[9], 0x8006)  # shade
        self.assertEqual(props[10], 1)
        self.assertEqual(props[11], -2 & 0xFFFF)

    def test_apply_writes_a_catalog_recipe(self):
        cli.main(["connect", "--mock", "--json"])
        code = cli.main(
            ["apply", "eterna-cinema", "--slot", "C7", "--yes", "--no-backup", "--mock", "--json"]
        )
        self.assertEqual(code, 0)
        state = json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))
        self.assertEqual(state["slots"][6]["name"], "Eterna Cinema")

    def test_backup_then_restore(self):
        cli.main(["connect", "--mock", "--json"])
        target = self.home / "bk.json"
        self.assertEqual(cli.main(["backup", "--out", str(target), "--mock", "--json"]), 0)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["slots"]), 7)
        self.assertEqual(cli.main(["restore", str(target), "--yes", "--mock", "--json"]), 0)

    def test_unknown_catalog_recipe_is_an_error(self):
        cli.main(["connect", "--mock", "--json"])
        self.assertEqual(cli.main(["apply", "nope", "--slot", "C1", "--mock", "--json"]), 2)


class PackagingTests(unittest.TestCase):
    def test_skill_and_readme_exist(self):
        for name in ("SKILL.md", "README.md", "LICENSE"):
            self.assertTrue((REPO / name).is_file(), f"{name} is missing")

    def test_skill_frontmatter_is_valid(self):
        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---\n")[1]
        self.assertIn("name:", frontmatter)
        self.assertIn("description:", frontmatter)


if __name__ == "__main__":
    unittest.main()
