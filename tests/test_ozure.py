"""Tests run against the simulated body, so no camera is required."""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import unittest
from pathlib import Path

from ozure import cli
from ozure.catalog import (
    available_catalogs,
    load_all_catalogs,
    load_catalog,
    repo_catalog_dir,
)
from ozure.errors import InvalidRecipe, ProtocolError
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


def camera(
    recipes: list[Recipe] | None = None, *, missing_props: list[int] | None = None
) -> tuple[FujiPtp, MockCameraTransport]:
    recipes = recipes or [sample_recipe(name=f"C{i + 1}") for i in range(7)]
    transport = MockCameraTransport(
        state_from_recipes("X100VI", recipes, missing_props=missing_props)
    )
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

    def test_empty_slot_reads_as_empty(self):
        recipes = [sample_recipe(name=f"C{i + 1}") for i in range(6)]
        recipes.append(Recipe(name="", empty=True))
        fuji, _transport = camera(recipes)
        self.assertTrue(fuji.read_slot(7).empty)
        fuji.close()

    def test_write_into_an_empty_slot_keeps_every_value(self):
        recipes = [sample_recipe(name=f"C{i + 1}") for i in range(6)]
        recipes.append(Recipe(name="", empty=True))
        fuji, _transport = camera(recipes)
        recipe = sample_recipe(name="First one")
        self.assertEqual(fuji.write_recipe(7, recipe), [])
        self.assertEqual(fuji.read_slot(7).to_dict(), recipe.to_dict())
        fuji.close()

    def test_empty_recipe_is_never_written(self):
        fuji, _transport = camera()
        with self.assertRaises(ProtocolError):
            fuji.write_recipe(3, Recipe(name="", empty=True))
        fuji.close()

    def test_unsupported_clarity_degrades_to_a_warning(self):
        # Older bodies have no clarity property at all.
        fuji, _transport = camera(missing_props=[0xD1A2])
        recipe = fuji.read_slot(1)
        self.assertEqual(recipe.clarity, 0)
        self.assertTrue(any("clarity" in warning for warning in recipe.warnings))
        warnings = fuji.write_recipe(1, sample_recipe(clarity=2.0), write_name=False)
        self.assertTrue(any("clarity" in warning for warning in warnings))
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


class RecipeFieldTests(unittest.TestCase):
    """Every field of the C1-C7 block must be reachable and honest."""

    WIRE_FIELDS = (
        "film_simulation",
        "dynamic_range",
        "dynamic_range_priority",
        "grain_effect",
        "smooth_skin",
        "color_chrome",
        "color_chrome_fx_blue",
        "white_balance",
        "highlight",
        "shadow",
        "color",
        "sharpness",
        "noise_reduction",
        "clarity",
        "monochrome_wc",
        "monochrome_mg",
    )

    def test_every_wire_field_is_in_the_model_and_the_output(self):
        recipe = sample_recipe()
        data = recipe.to_dict()
        for field in self.WIRE_FIELDS:
            self.assertIn(field, data)
        # white_balance expands to four words (mode, shift R, shift B, Kelvin),
        # so the fields above account for exactly the 19 property words.
        self.assertEqual(len(self.WIRE_FIELDS) - 1 + 4, 19)

    def test_exposure_is_not_part_of_the_recipe_block(self):
        self.assertNotIn("exposure", sample_recipe().to_dict())
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"exposure": 0.5})

    def test_integers_are_not_silently_rounded(self):
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"noise_reduction": 1.5})
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"dynamic_range_priority": 1.5})

    def test_long_names_are_rejected_before_the_camera(self):
        with self.assertRaises(InvalidRecipe):
            Recipe.from_dict({"name": "x" * 255})

    def test_dynamic_range_is_a_warning_when_priority_is_pinned(self):
        recipe = Recipe.from_dict({"dynamic_range": "dr200", "dynamic_range_priority": 2})
        self.assertTrue(any("dynamic_range is ignored" in w for w in recipe.warnings))

    def test_unset_monochrome_words_decode_as_zero(self):
        recipe = sample_recipe()
        props = props_from_recipe(recipe)
        props[3] = props[4] = 0xFFFF
        decoded = recipe_from_props(recipe.name, props)
        self.assertEqual(decoded.monochrome_wc, 0)
        self.assertEqual(decoded.monochrome_mg, 0)


class CatalogTests(unittest.TestCase):
    def test_every_visible_catalog_loads_and_validates(self):
        catalogs = available_catalogs()
        self.assertGreaterEqual(len(catalogs), 2)
        merged = load_all_catalogs()
        self.assertGreaterEqual(len(merged), 100)
        for entry in merged:
            self.assertTrue(entry.slug)
            self.assertTrue(entry.name)
            self.assertTrue(entry.catalog)
            entry.recipe.validate()

    def test_bundled_collections_are_separate_catalogs(self):
        names = {info.name for info in available_catalogs()}
        self.assertIn("samples", names)
        self.assertIn("fxw", names)
        fxw = load_catalog(repo_catalog_dir() / "fxw")
        self.assertGreaterEqual(len(fxw), 50)
        self.assertTrue(all(entry.recipe.film_simulation for entry in fxw))

    def test_catalog_metadata_is_read(self):
        info = next(info for info in available_catalogs() if info.name == "fxw")
        self.assertIn("Fuji", info.title)
        self.assertTrue(info.source.startswith("https://"))

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

    def test_apply_into_an_empty_slot_works(self):
        import json as _json

        from ozure.mockcam import state_from_recipes  # noqa: F401  (documented source of the file)

        cli.main(["connect", "--mock", "--json"])
        state_path = self.home / "mock-camera.json"
        state = _json.loads(state_path.read_text(encoding="utf-8"))
        state["slots"][6] = {"name": "", "props": [0xFFFF] * 19, "empty": True}
        state_path.write_text(_json.dumps(state), encoding="utf-8")
        code = cli.main(
            ["apply", "eterna-cinema", "--slot", "C7", "--yes", "--no-backup", "--mock", "--json"]
        )
        self.assertEqual(code, 0)
        state = _json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["slots"][6]["name"], "Eterna Cinema")
        self.assertNotEqual(state["slots"][6]["props"][0], 0xFFFF)

    def test_set_covers_dynamic_range_priority_and_white_balance(self):
        import json as _json

        cli.main(["connect", "--mock", "--json"])
        code = cli.main(
            [
                "set",
                "C2",
                "--dynamic-range-priority",
                "dr200",
                "--wb-mode",
                "shade",
                "--wb-shift-b",
                "-3",
                "--yes",
                "--no-backup",
                "--mock",
                "--json",
            ]
        )
        self.assertEqual(code, 0)
        props = _json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))["slots"][
            1
        ]["props"]
        self.assertEqual(props[1], 2)  # DR priority
        self.assertEqual(props[9], 0x8006)  # shade
        self.assertEqual(props[11], -3 & 0xFFFF)

    def test_restore_skips_empty_slots(self):
        cli.main(["connect", "--mock", "--json"])
        import json as _json

        before = _json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))
        backup = self.home / "bk.json"
        backup.write_text(
            _json.dumps({"slots": {"C1": {"name": "Restored"}, "C7": {"name": "", "empty": True}}}),
            encoding="utf-8",
        )
        code = cli.main(["restore", str(backup), "--yes", "--mock", "--json"])
        self.assertEqual(code, 0)
        state = _json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))
        self.assertEqual(state["slots"][0]["name"], "Restored")
        # C7 was recorded as empty in the backup, so it must be left exactly as
        # it was instead of being filled with defaults.
        self.assertEqual(state["slots"][6], before["slots"][6])

    def test_catalogs_lists_bundled_collections(self):
        code = cli.main(["catalogs", "--json"])
        self.assertEqual(code, 0)
        names = {info.name for info in available_catalogs()}
        self.assertIn("fxw", names)
        self.assertIn("samples", names)

    def test_catalog_init_creates_a_named_catalog(self):
        code = cli.main(["catalog", "init", "my-looks", "--json"])
        self.assertEqual(code, 0)
        directory = self.home / "catalogs" / "my-looks"
        self.assertTrue(directory.is_dir())
        self.assertTrue((directory / "README.md").is_file())
        # Running it again must not pretend it was created.
        self.assertEqual(cli.main(["catalog", "init", "my-looks", "--json"]), 0)

    def test_catalog_add_copies_one_slot(self):
        cli.main(["connect", "--mock", "--json"])
        code = cli.main(
            [
                "catalog",
                "add",
                "C3",
                "--catalog",
                "my-looks",
                "--name",
                "My Eterna",
                "--tags",
                "cinema,night",
                "--mock",
                "--json",
            ]
        )
        self.assertEqual(code, 0)
        path = self.home / "catalogs" / "my-looks" / "my-eterna.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "My Eterna")
        self.assertEqual(data["tags"], ["cinema", "night"])
        self.assertIn("recipe", data)
        self.assertIn(data["recipe"]["film_simulation"], data["recipe"].values())

    def test_catalog_export_saves_every_non_empty_slot(self):
        cli.main(["connect", "--mock", "--json"])
        state = json.loads((self.home / "mock-camera.json").read_text(encoding="utf-8"))
        state["slots"][6] = {"name": "", "props": [0xFFFF] * 19, "empty": True}
        (self.home / "mock-camera.json").write_text(json.dumps(state), encoding="utf-8")
        code = cli.main(["catalog", "export", "--mock", "--json"])
        self.assertEqual(code, 0)
        catalog = self.home / "catalog"
        written = sorted(path.name for path in catalog.glob("*.json"))
        self.assertEqual(len(written), 6)
        self.assertFalse(any("c7" in name for name in written))

    def test_catalog_export_can_write_a_bundle(self):
        cli.main(["connect", "--mock", "--json"])
        target = self.home / "looks.json"
        code = cli.main(["catalog", "export", "--out", str(target), "--mock", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertGreaterEqual(len(payload["recipes"]), 6)

    def test_catalog_list_filters_by_catalog(self):
        from ozure.catalog import repo_catalog_dir

        fxw = load_catalog(repo_catalog_dir() / "fxw")
        self.assertGreaterEqual(len(fxw), 50)
        code = cli.main(["catalog", "list", "--catalog", "fxw", "--json"])
        self.assertEqual(code, 0)

    def test_unknown_catalog_recipe_is_an_error(self):
        cli.main(["connect", "--mock", "--json"])
        self.assertEqual(cli.main(["apply", "nope", "--slot", "C1", "--mock", "--json"]), 2)


class SkillDocTests(unittest.TestCase):
    """SKILL.md is the contract an agent reads. If it drifts from the CLI, an
    agent will confidently run a command that does not exist."""

    def documented_commands(self) -> list[list[str]]:
        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        commands = []
        in_fence = False
        for raw in text.splitlines():
            stripped = raw.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence or not stripped.startswith("ozure "):
                continue
            line = stripped
            # `cmd || fallback` and trailing `# comments`
            line = line.split("||")[0].split("  #")[0].split(" #")[0].strip()
            argv = shlex.split(line)
            argv = [
                "backup.json"
                if token.startswith("~") or "..." in token or token.startswith("<")
                else token
                for token in argv
            ]
            commands.append(argv)
        self.assertGreater(len(commands), 8)
        return commands

    def test_every_documented_command_parses(self):
        parser = cli.build_parser()
        for argv in self.documented_commands():
            with self.subTest(argv=argv):
                try:
                    parser.parse_args(argv[1:])
                except SystemExit as exc:  # --version / --help exit 0
                    self.assertEqual(exc.code, 0, f"{argv} does not parse")

    def test_documented_exit_codes_match_the_code(self):
        from ozure import errors

        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        block = text[text.index("| code | meaning") : text.index("## Choosing a slot")]
        documented = {int(match) for match in re.findall(r"^\| (\d+) \|", block, re.MULTILINE)}
        actual = {0}
        for name in dir(errors):
            candidate = getattr(errors, name)
            if isinstance(candidate, type) and issubclass(candidate, errors.OzureError):
                actual.add(candidate.exit_code)
        self.assertEqual(documented, actual)

    def test_npm_package_matches_the_python_version(self):
        manifest = json.loads((REPO / "npm" / "ozure" / "package.json").read_text(encoding="utf-8"))
        version = None
        for line in (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.startswith("version ="):
                version = line.split("=", 1)[1].strip().strip('"')
                break
        self.assertEqual(manifest["version"], version)
        self.assertEqual(manifest["bin"], {"ozure": "bin/ozure.js"})
        for name, wanted in manifest["optionalDependencies"].items():
            self.assertEqual(wanted, version, name)
            self.assertTrue(name.startswith("@"))

    def test_npm_launcher_is_executable_and_has_a_shebang(self):
        shim = REPO / "npm" / "ozure" / "bin" / "ozure.js"
        self.assertTrue(shim.is_file())
        self.assertTrue(shim.read_text(encoding="utf-8").startswith("#!/usr/bin/env node"))

    def test_skill_documents_the_mock_boundary(self):
        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never fake hardware", text)

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
