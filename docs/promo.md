# Promo

`assets/promo.mp4` — 36 s, 1280×720, H.264, silent, and every line of narration
is burned in, so it works muted (which is how Twitter plays it).

Regenerate it (it runs the real CLI against the simulated body, so it can never
show a command that does not work):

```bash
python tools/build_promo.py --poster 3.2        # English (the cut in assets/)
python tools/build_promo.py --lang es --poster 3.2   # Spanish
```

`assets/promo-poster.png` is a still from the intro, useful as a thumbnail.
A local copy (video, poster, tweet text and this file) lives in
`~/Videos/ozure-promo/`.

## Copy for the post

Spanish:

> Tu Fujifilm guarda 7 recetas. Hasta ahora solo se tocaban con la rueda.
>
> **ozure** las lee, las edita y las reinstala por USB. 126 recetas de Fuji X
> Weekly, Osan-Bilgi, Alex Armitage… o las tuyas, exportadas de la cámara.
>
> Sin GUI, sin tarjetas. Dry-run por defecto, backup y verificación en cada
> escritura. También es un skill para tu agente.
>
> github.com/AlPeFe/ozure

English:

> Your Fujifilm body stores seven custom recipes. Until now you edited them with
> the dial.
>
> **ozure** reads them, edits them and installs them over USB — 126 recipes from
> Fuji X Weekly, Osan-Bilgi, Alex Armitage… or your own, exported from the
> camera.
>
> No GUI, no cards. Dry-run by default, backup + read-back verification on every
> write. It is also an agent skill.
>
> github.com/AlPeFe/ozure

Thread idea (3 posts): the 7-slot problem → the CLI (dry run + verification) →
the catalogs and the skill, with one image each.

## Alt text (accessibility)

> A 36-second screen recording: a pastel pink jellyfish logo, then a terminal
> running `ozure connect`, `ozure list`, `ozure apply kodak-gold-200 --slot C6`
> as a dry run, the same command with `--yes`, and a catalog table with 126
> recipes.
