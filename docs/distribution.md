# Distribution

ozure is a Python CLI with a small, dependency-free core: that makes `pip` the
front door and lets everything else wrap it.

## 1. PyPI (the real one)

```bash
python -m pip install build
python -m build                      # dist/ozure-x.y.z.tar.gz + wheel
python -m twine upload dist/*        # or: uv publish
```

Users then get it in one line:

```bash
pipx install "ozure[usb]"     # isolated CLI, best for most people
uvx --from "ozure[usb]" ozure # no install at all
pip install "ozure[usb]"      # inside an existing environment
```

`[usb]` pulls `pyusb`; without it the CLI still runs `--mock` and `catalog`.

**Do it from CI, not from your laptop.** PyPI's Trusted Publishing needs no
token: register the repo + workflow on PyPI, then tag:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

`tools/publish-pypi.yml` is the workflow (copy it to `.github/workflows/`, it
needs the `workflow` scope on the token).

## 2. npm

npm cannot install a Python package, so there are two honest options:

**a) Wrapper that calls the Python CLI (simple, fragile).** Publish a package
whose `bin` is a Node shim:

```js
#!/usr/bin/env node
// spawn the python module, pass args through
```

It only works if the user already has Python + `pip install ozure`. Fine for an
internal tool, bad for strangers.

**b) Prebuilt binaries (what esbuild/swc do).** Build standalone executables
and publish one npm package per platform, with `optionalDependencies`:

```
ozure            # bin shim: find the right binary, exec it
ozure-win32-x64  # ozure.exe
ozure-darwin-arm64
ozure-linux-x64
```

The shim resolves `require.resolve('ozure-' + process.platform + '-' + process.arch)`
and `execFile`s it. No Python needed on the user's machine.

Build the binaries with PyInstaller (one file per OS):

```bash
python -m pip install pyinstaller
pyinstaller --onefile --name ozure --add-data "ozure/data/catalog:ozure/data/catalog" ozure/__main__.py
```

`tools/ozure.spec` is the reproducible version of that command. Cross-compiling
is not a thing: build on each OS (GitHub Actions matrix), then upload the three
artifacts to a GitHub Release and point the npm packages at them.

## 3. Homebrew (macOS)

One formula in a tap (`AlPeFe/homebrew-tap`):

```ruby
class Ozure < Formula
  include Language::Python::Virtualenv
  desc "Fujifilm custom recipes over USB PTP"
  homepage "https://github.com/AlPeFe/ozure"
  url "https://files.pythonhosted.org/packages/.../ozure-0.2.0.tar.gz"
  sha256 "..."
  depends_on "python@3.12"
  def install
    virtualenv_install_with_resources
  end
end
```

```bash
brew install AlPeFe/tap/ozure
```

`brew create <sdist-url>` generates the skeleton, `brew audit --strict` checks it.

## 4. Scoop (Windows)

A manifest in `AlPeFe/scoop-bucket`, pointing at the PyInstaller zip from the
GitHub Release:

```json
{
  "version": "0.2.0",
  "url": "https://github.com/AlPeFe/ozure/releases/download/v0.2.0/ozure-win32-x64.zip",
  "bin": "ozure.exe",
  "hash": "..."
}
```

```powershell
scoop bucket add alpefe https://github.com/AlPeFe/scoop-bucket
scoop install ozure
```

## 5. GitHub Releases

Even with no package manager, `Releases` is the fallback people understand:
`ozure-win32-x64.zip`, `ozure-darwin-arm64.tar.gz`, `ozure-linux-x64.tar.gz`,
plus the sdist/wheel. Attach the promo video and a one-line install snippet to
the release notes.

## What ships in the wheel

The recipe catalogs live inside the package (`ozure/data/catalog/`), so
`pip install ozure` has the 126 recipes offline. Verify before every release:

```bash
python -m build
python -c "import zipfile,glob; n=zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist(); print(sum(x.endswith('.json') for x in n), 'json files')"
```

## Checklist for a release

1. Bump `version` in `pyproject.toml`, `ozure/__init__.py` and `SKILL.md`.
2. `python -m unittest discover -s tests` · `ruff check .`
3. `python -m build` and install the wheel in a clean venv; run
   `ozure catalogs` from a directory that is not the repo.
4. Tag `vX.Y.Z`, let `publish-pypi.yml` upload.
5. PyInstaller matrix → GitHub Release → npm / Scoop / Homebrew point at it.
6. Update `README.md` install block and the `SKILL.md` metadata version.
