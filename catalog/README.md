# Catalog

These five recipes are **samples**: they exist so the CLI, the tests and the demo
have something to work with. Replace them with your own collection — the folder
*is* the catalog, no code changes needed.

Add files here (or in `~/.ozure/catalog/`, which overrides on slug collisions)
in the format described in [`../docs/catalog-format.md`](../docs/catalog-format.md):

```json
{
  "slug": "portra-soft",
  "name": "Portra Soft",
  "author": "...",
  "tags": ["color", "portrait"],
  "recipe": { "film_simulation": "pro_neg_hi", "highlight": -0.5, "shadow": 0.5 }
}
```

Then:

```bash
ozure catalog list
ozure apply portra-soft --slot C4           # dry run
ozure apply portra-soft --slot C4 --yes     # write + verify
```
