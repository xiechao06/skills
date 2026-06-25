---
name: safe-clean-my-mac
description: Reclaim disk space on macOS dev machines by safely clearing package caches, build artifacts, Xcode debug symbols, browser caches, VS Code workspace data, and optional old Android SDK components.
---

# safe-clean-my-mac

Safe disk cleanup for macOS development machines. Reclaims gigabytes of space from package caches, build artifacts, Xcode debug symbols, browser caches, VS Code workspace data, and optionally old Android SDK components — without touching user projects, downloads, or active dev toolchains.

## When to use

- User says "my disk is almost full", "clean my Mac", "free up space", or "Mac storage full"
- Before a major cleanup of a development macOS machine
- When reclaiming space from caches, build artifacts, and SDK leftovers

## What it cleans (safe defaults)

| Category | Locations | Typical reclaim |
|---|---|---|
| Python package caches | `~/.cache/uv`, pip cache, `~/.cache/huggingface`, `~/.cache/codex-runtimes` | 5–8 GB |
| JavaScript package caches | `~/.npm`, yarn cache, `~/.cache/pnpm` | 1–3 GB |
| Rust / C++ caches | `~/.cargo` (autoclean), `~/vcpkg/buildtrees`, `~/vcpkg/packages`, `~/.cache/vcpkg/archives` | 5–10 GB |
| Java / Android build caches | `~/.gradle/caches`, `~/.m2/repository` | 1–3 GB |
| Xcode leftovers | Old `iOS DeviceSupport` symbols (keeps newest), CoreSimulator caches | 2–5 GB |
| Browser caches | Comet/Chrome `CacheStorage`, `GPUCache`, crashpad, extension CRX cache | 2–5 GB |
| VS Code data | `workspaceStorage` (Copilot indexes), `CachedExtensionVSIXs`, `Crashpad` | 2–5 GB |
| Application leftovers | Docker `in_progress` installer, Puppeteer cache | 1–3 GB |

## What it does NOT touch

- User projects in `~/workspace`, `~/Documents`, `~/Downloads`, `~/Desktop`
- Active dev toolchains (`~/Qt`, `~/flutter`, latest Android NDK, current Xcode symbols)
- Comet/Chrome extensions, history, cookies, login data, bookmarks
- Docker/OrbStack active virtual disk data

## Usage

Run the included script from the skill directory:

```bash
cd skills/safe-clean-my-mac
bash ./clean-mac.sh
```

After installing the package with pi, the agent can also run it from the skill directory using its relative path.

With optional Android SDK cleanup (keeps only the latest NDK + `android-36/google_apis`):

```bash
bash ./clean-mac.sh --android
```

With dry-run preview (shows what would be removed without deleting):

```bash
bash ./clean-mac.sh --dry-run
```

## Recovery impact

- All removed package caches are re-downloadable on next build/run.
- vcpkg `buildtrees`/`packages` are rebuilt on demand.
- VS Code `workspaceStorage` rebuilds when reopening workspaces; Copilot indexes regenerate.
- Browser caches rebuild on next website visit.
- Old Android NDKs/system images must be re-installed manually if needed.
