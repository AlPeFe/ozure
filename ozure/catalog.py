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
from .recipe import Recipe


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
    override = os.environ.get("OZURE_HOME")
    base = Path(override) if override else Path.home() / ".ozure"
    return base / "catalog"


def resolve_catalog_dir(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_dir():
            raise UsageError(f"catalog directory not found: {path}")
        return path
    env = os.environ.get("OZURE_CATALOG")
    if env:
        path = Path(env).expanduser()
        if not path.is_dir():
            raise UsageError(f"$OZURE_CATALOG is not a directory: {path}")
        return path
    for candidate in (repo_catalog_dir(), user_catalog_dir()):
        if candidate.is_dir():
            return candidate
    return user_catalog_dir()


def _slugify(text: str) -> str:
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
    slug = str(entry.get("slug") or _slugify(name))
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
    """Load every JSON file under `directory`, sorted by name."""
    if not directory.is_dir():
        return []
    recipes: list[CatalogRecipe] = []
    for path in sorted(directory.rglob("*.json")):
        if path.name.startswith("."):
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
    # Later files win on slug collisions so a user catalog can override the
    # bundled samples.
    seen: dict[str, CatalogRecipe] = {}
    for recipe in recipes:
        seen[recipe.slug] = recipe
    return sorted(seen.values(), key=lambda item: item.slug)


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
