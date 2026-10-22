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

## 2. npm (wired up)

```bash
npm install -g ozure
```

That is a thin launcher plus one package per platform, the esbuild pattern:

```
npm/ozure                 ozure                    bin/ozure.js (launcher)
npm/ozure-win32-x64       ozure-win32-x64          bin/ozure.exe
npm/ozure-darwin-arm64    ...                        (built by CI)
npm/ozure-linux-x64       ...
```

`tools/build_npm.py` stamps the scope/version from `pyproject.toml`, builds the
binary with PyInstaller, copies it into the platform package and can `npm pack`
them. Verified locally with `npm install -g --prefix <dir> <tarballs>`: the
launcher finds its binary and `ozure catalogs` works with no Python present.

Publishing (logged in as `alpefe`, the packages go out scoped):

```bash
python tools/build_npm.py --scope alpefe --pack
python tools/publish_npm.py            # platforms first, launcher last
```

`publish_npm.py` also takes `--dry-run`, skips packages whose binary has not
been built yet, and `--stage` / `--approve` for the staged flow.

### Staged publishing, in practice

Newer npm accounts get **stage-only** credentials: `npm publish` answers
`EOTP`, and the two-step flow is the only way in.

1. `python tools/publish_npm.py --stage` — writes pending versions. The staging
   endpoint sometimes answers `403 ... request timeout after 30000ms`; it is a
   registry hiccup, retry (the script does, three times).
2. `npm stage list` — check `status` is `staged` (a just-created entry can say
   `validating` for a few seconds; approving too early gives a confusing 404).
3. `python tools/publish_npm.py --approve` — promotes the binaries first and the
   launcher last. **This is the step that needs 2FA**, so it only works from an
   interactive terminal: npm opens the browser and the passkey confirms it.
4. `npm view @alpefe/ozure version` once the registry settles.

**2FA**: if the npm account requires a one-time password for publishing, npm
prints `EOTP` and opens an auth URL. Either type the code when prompted, or
create an **Automation** token (Account → Access Tokens → Automation) and put it
in `~/.npmrc`:

```
//registry.npmjs.org/:_authToken=npm_XXXXXXXX
```

Automation tokens bypass 2FA — that is also what the `NPM_TOKEN` secret in
`tools/publish-pypi.yml` must be.

The scope is optional: `ozure` is free on npm, so the default is unscoped. If
you prefer your namespace, `python tools/build_npm.py --scope alpefe` produces
`@alpefe/ozure` and `@alpefe/ozure-<platform>` instead (both were free when this
was written).

Platform packages must be published **before** the launcher, so its
`optionalDependencies` resolve. `tools/publish-pypi.yml` has an `npm` job that
does this from the Release artifacts.

The launcher falls back to `python -m ozure` when the platform binary is missing,
and prints the install options when neither exists.

### The alternatives, for the record

npm cannot install a Python package, so before choosing the launcher there were
two honest options:

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
