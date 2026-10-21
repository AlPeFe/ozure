"""Recipe catalog: JSON files on disk, discovered and searched.

A catalog is just a directory. Each file is either one recipe or
``{"recipes": [...]}``, which makes it easy to paste a large collection without
touching code. The directory is looked up in this order:

1. ``--catalog PATH``
2. ``$OZURE_CATALOG``
3. ``<repo>/catalog`` next to this package
4. ``~/.ozure/catalog``
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InvalidRecipe, UsageError
from .paths import catalogs_root, default_catalog_dir
from .recipe import Recipe

newline = chr(10)

#: A catalog directory may carry this file to describe itself.
META_FILE = "catalog.json"


@dataclass
class CatalogRecipe:
    slug: str
    name: str
    recipe: Recipe
    author: str | None = None
    source: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)
    path: Path | None = None
    catalog: str | None = None

    @property
    def film(self) -> str:
        return self.recipe.film_simulation

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "slug": self.slug,
            "name": self.name,
            "film_simulation": self.recipe.film_simulation,
            "tags": self.tags,
            "recipe": self.recipe.to_dict(),
        }
        for key in ("author", "source", "notes"):
            value = getattr(self, key)
            if value:
                data[key] = value
        if self.path:
            data["path"] = str(self.path)
        if self.catalog:
            data["catalog"] = self.catalog
        return data

    def matches(self, query: str) -> bool:
        needle = query.strip().lower()
        if not needle:
            return True
        haystack = " ".join(
            [
                self.slug,
                self.name,
                self.recipe.film_simulation,
                " ".join(self.tags),
                self.notes or "",
                self.author or "",
            ]
        ).lower()
        return all(part in haystack for part in needle.split())


def repo_catalog_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "catalog"


def user_catalog_dir() -> Path:
    return default_catalog_dir()


@dataclass
class CatalogInfo:
    """One catalog (a directory) as shown by `ozure catalogs`."""

    name: str
    path: Path
    kind: str  # bundled | user | default
    title: str = ""
    tagline: str = ""
    source: str = ""
    recipes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "kind": self.kind,
            "title": self.title or self.name,
            "tagline": self.tagline,
            "source": self.source,
            "recipes": self.recipes,
            "exists": self.path.is_dir(),
        }


def read_meta(directory: Path) -> dict[str, Any]:
    meta = directory / META_FILE
    if not meta.is_file():
        return {}
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def available_catalogs() -> list[CatalogInfo]:
    """Every catalog the user can reach, bundled first, then their own."""
    catalogs: list[CatalogInfo] = []
    bundled_root = repo_catalog_dir()
    if bundled_root.is_dir():
        for directory in sorted(bundled_root.iterdir()):
            if not directory.is_dir() or not any(directory.glob("*.json")):
                continue
            meta = read_meta(directory)
            catalogs.append(
                CatalogInfo(
                    name=directory.name,
                    path=directory,
                    kind="bundled",
                    title=str(meta.get("name", directory.name)),
                    tagline=str(meta.get("tagline", "")),
                    source=str(meta.get("source", "")),
                    recipes=len(load_catalog(directory)),
                )
            )
    local = user_catalog_dir()
    if local.is_dir() and any(local.glob("*.json")):
        catalogs.append(
            CatalogInfo(
                name="local",
                path=local,
                kind="default",
                title="My catalog",
                recipes=len(load_catalog(local)),
            )
        )
    root = catalogs_root()
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            meta = read_meta(directory)
            catalogs.append(
                CatalogInfo(
                    name=directory.name,
                    path=directory,
                    kind="user",
                    title=str(meta.get("name", directory.name)),
                    tagline=str(meta.get("tagline", "")),
                    source=str(meta.get("source", "")),
                    recipes=len(load_catalog(directory)),
                )
            )
    return catalogs


def resolve_catalog_dir(explicit: str | None = None, *, create: bool = False) -> Path:
    """Where a catalog lives.

    ``None`` means the user's own catalog (~/.ozure/catalog), which is created on
    demand when writing. A bare name looks for a bundled catalog first, then for
    one of the user's named catalogs; anything with a separator is a path.
    Reading tolerates a directory that does not exist yet: an empty catalog is a
    valid answer, and it is what lets an agent offer to create one.
    """
    if explicit in ("local", "default"):
        return user_catalog_dir()
    if explicit:
        path = Path(explicit).expanduser()
        is_name = not any(sep in explicit for sep in ("/", "\\", ":")) and not path.exists()
        if is_name:
            # A bare name is a catalog name, not a relative directory: bundled
            # collections first, then the user's named catalogs. Writing with a
            # new name creates ~/.ozure/catalogs/<name>.
            bundled = repo_catalog_dir() / explicit
            named = catalogs_root() / explicit
            path = bundled if bundled.is_dir() else named
    else:
        env = os.environ.get("OZURE_CATALOG")
        path = Path(env).expanduser() if env else user_catalog_dir()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def new_catalog_dir(name: str | None, explicit: str | None) -> Path:
    """Resolve the directory for `catalog init`: existing default, named or explicit."""
    if explicit:
        return Path(explicit).expanduser()
    if name:
        return catalogs_root() / slugify(name)
    return user_catalog_dir()


CATALOG_README = """# Recipes

A catalog is just this folder: one JSON file per recipe, or a single file with
`{"version": 1, "recipes": [...]}`.

    {
      "slug": "acros-night",
      "name": "Acros Night",
      "tags": ["monochrome"],
      "recipe": { "film_simulation": "acros", "highlight": 1, "shadow": 2 }
    }

Useful commands:

    ozure catalog list
    ozure apply acros-night --slot C3
    ozure catalog add C3 --name "My look"     # copy a slot from the camera
    ozure catalog export                      # save every slot to this folder

Full schema: `ozure catalog format`.
"""


def write_catalog_readme(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "README.md"
    if not path.exists():
        path.write_text(CATALOG_README, encoding="utf-8")
    return path


def slugify(text: str) -> str:
    """`Reggie's B&W` -> `reggies-bw`; used for file names and slugs."""
    text = text.replace("'", "").replace("’", "").replace("&", "")
    out = []
    for ch in text.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


CATALOG_META_KEYS = frozenset(
    {"slug", "author", "source", "notes", "tags", "description", "version"}
)


def unique_slug(directory: Path, base: str, reserved: Iterable[str] = ()) -> str:
    """A slug nobody uses yet: `acros-night`, `acros-night-2`, ..."""
    taken = {entry.slug for entry in load_catalog(directory)} | set(reserved)
    slug = base or "recipe"
    index = 1
    while slug in taken:
        index += 1
        slug = f"{base}-{index}"
    return slug


def entry_to_json(entry: CatalogRecipe) -> dict[str, Any]:
    """The canonical on-disk shape: no derived fields, no absolute paths."""
    data: dict[str, Any] = {"slug": entry.slug, "name": entry.name}
    for key in ("author", "source", "notes"):
        value = getattr(entry, key)
        if value:
            data[key] = value
    if entry.tags:
        data["tags"] = list(entry.tags)
    data["recipe"] = entry.recipe.to_dict()
    return data


def write_entry(directory: Path, entry: CatalogRecipe, *, force: bool = False) -> Path:
    """Write one recipe as `<slug>.json`. Refuses to clobber unless forced."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entry.slug}.json"
    if path.exists() and not force:
        raise UsageError(
            f"{path.name} already exists in {directory}",
            hint="pick another --slug/--name, or pass --force to overwrite",
        )
    path.write_text(
        json.dumps(entry_to_json(entry), indent=2, ensure_ascii=False) + newline,
        encoding="utf-8",
    )
    return path


def write_bundle(path: Path, entries: list[CatalogRecipe]) -> Path:
    """Write several recipes into a single file: {"version": 1, "recipes": [...]}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "recipes": [entry_to_json(entry) for entry in entries],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + newline, encoding="utf-8")
    return path


def _recipe_from_entry(entry: dict[str, Any], path: Path) -> CatalogRecipe:
    payload = entry.get("recipe")
    if payload is None:
        # Flat file: the recipe fields live at the top level next to the metadata.
        payload = {key: value for key, value in entry.items() if key not in CATALOG_META_KEYS}
    try:
        recipe = Recipe.from_dict(payload)
    except InvalidRecipe as exc:
        raise InvalidRecipe(f"{path.name}: {exc.message}", hint=exc.hint) from exc
    name = str(entry.get("name") or recipe.name or path.stem)
    recipe.name = name
    slug = str(entry.get("slug") or slugify(name))
    tags = entry.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return CatalogRecipe(
        slug=slug,
        name=name,
        recipe=recipe,
        author=entry.get("author"),
        source=entry.get("source"),
        notes=entry.get("notes") or entry.get("description"),
        tags=[str(tag) for tag in tags],
        path=path,
    )


def load_catalog(directory: Path) -> list[CatalogRecipe]:
    """Load the recipes of ONE catalog: the JSON files directly inside it.

    Subdirectories are catalogs of their own, not part of the parent, which is
    what makes `catalog/fxw`, `catalog/samples` and `~/.ozure/catalogs/<name>`
    addressable one by one.
    """
    if not directory.is_dir():
        return []
    recipes: list[CatalogRecipe] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith(".") or path.name == META_FILE:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidRecipe(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno})") from exc
        entries = data.get("recipes") if isinstance(data, dict) else None
        if isinstance(entries, list):
            for entry in entries:
                recipes.append(_recipe_from_entry(entry, path))
        elif isinstance(data, dict):
            recipes.append(_recipe_from_entry(data, path))
        else:
            raise InvalidRecipe(f"{path}: expected a JSON object")
    seen: dict[str, CatalogRecipe] = {}
    for recipe in recipes:
        seen[recipe.slug] = recipe
    return sorted(seen.values(), key=lambda item: item.slug)


def load_all_catalogs() -> list[CatalogRecipe]:
    """Every recipe the user can reach, tagged with the catalog it came from.

    The user's own catalog wins on slug collisions, then named catalogs, then
    the bundled collections.
    """
    order = {"default": 0, "user": 1, "bundled": 2}
    catalogs = sorted(available_catalogs(), key=lambda info: order.get(info.kind, 3))
    merged: dict[str, CatalogRecipe] = {}
    for info in catalogs:
        for entry in load_catalog(info.path):
            entry.catalog = info.name
            merged.setdefault(entry.slug, entry)
    return sorted(merged.values(), key=lambda item: (item.catalog or "", item.slug))


def find(catalog: Iterable[CatalogRecipe], ref: str) -> CatalogRecipe:
    text = ref.strip()
    candidates = list(catalog)
    for recipe in candidates:
        if recipe.slug == text:
            return recipe
    lowered = text.lower()
    for recipe in candidates:
        if recipe.name.lower() == lowered or recipe.slug.lower() == lowered:
            return recipe
    partial = [
        recipe for recipe in candidates if lowered in recipe.slug or lowered in recipe.name.lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if partial:
        options = ", ".join(recipe.slug for recipe in partial[:8])
        raise UsageError(f"{text!r} is ambiguous", hint=f"candidates: {options}")
    raise UsageError(
        f"no recipe called {text!r} in the catalog",
        hint="run `ozure catalog list` to see what is there",
    )
