#!/usr/bin/env bash
#
# safe-clean-my-mac
# Reclaim disk space on macOS dev machines without touching user projects.
#
# Usage:
#   clean-mac.sh [--android] [--dry-run]

set -euo pipefail

DRY_RUN=false
CLEAN_ANDROID=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true ; shift ;;
    --android) CLEAN_ANDROID=true ; shift ;;
    -h|--help)
      echo "Usage: $0 [--android] [--dry-run]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[DRY-RUN] would run: $*"
  else
    echo "===> $*"
    "$@"
  fi
}

rmrf() {
  for p in "$@"; do
    if [[ -e "$p" ]]; then
      if [[ "$DRY_RUN" == true ]]; then
        echo "[DRY-RUN] would remove: $p ($(du -sh "$p" 2>/dev/null | cut -f1))"
      else
        echo "Removing: $p"
        rm -rf "$p"
      fi
    fi
  done
}

before=$(df -h /System/Volumes/Data | awk 'NR==2{print $5}')
echo "Disk usage before cleanup: $before"
echo ""

# --- Python / AI caches ---
if command -v uv >/dev/null 2>&1; then
  run uv cache clean 2>/dev/null || rmrf ~/.cache/uv/archive-v0/* ~/.cache/uv/sdists-v9/* ~/.cache/uv/git-v0/* ~/.cache/uv/simple-v20/* ~/.cache/uv/simple-v16/* ~/.cache/uv/binaries-v0/* ~/.cache/uv/builds-v0/* ~/.cache/uv/wheels-v6/* ~/.cache/uv/wheels-v5/*
fi
if command -v pip >/dev/null 2>&1; then
  run pip cache purge 2>/dev/null || true
fi
rmrf ~/.cache/huggingface/* ~/.cache/codex-runtimes/*

# --- JavaScript caches ---
if command -v npm >/dev/null 2>&1; then
  run npm cache clean --force 2>/dev/null || true
fi
if command -v yarn >/dev/null 2>&1; then
  run yarn cache clean --all 2>/dev/null || true
fi
rmrf ~/.cache/pnpm/*

# --- Rust cache ---
if command -v cargo >/dev/null 2>&1; then
  run cargo cache --autoclean 2>/dev/null || true
  run cargo cache -e 2>/dev/null || true
fi

# --- vcpkg build artifacts ---
rmrf ~/vcpkg/buildtrees/* ~/vcpkg/packages/* ~/.cache/vcpkg/archives/*

# --- Java / Android build caches ---
rmrf ~/.gradle/caches/* ~/.gradle/daemon/* ~/.gradle/wrapper/dists/* ~/.gradle/native/*
rmrf ~/.m2/repository/*

# --- Xcode: keep only newest iOS DeviceSupport ---
DEVICE_SUPPORT_DIR="$HOME/Library/Developer/Xcode/iOS DeviceSupport"
if [[ -d "$DEVICE_SUPPORT_DIR" ]]; then
  newest=$(ls -1 "$DEVICE_SUPPORT_DIR" 2>/dev/null | sort -V | tail -n 1)
  for dir in "$DEVICE_SUPPORT_DIR"/*; do
    name=$(basename "$dir")
    if [[ -d "$dir" && "$name" != "$newest" ]]; then
      rmrf "$dir"
    fi
  done
fi
rmrf ~/Library/Developer/Xcode/DerivedData/*

# --- Application leftovers ---
rmrf ~/Library/Application\ Support/com.docker.install/in_progress/*
rmrf ~/.cache/puppeteer/*

# --- Browser caches (Comet / Chrome-like) ---
for profile in "$HOME/Library/Application Support/Comet" "$HOME/Library/Application Support/Google/Chrome"; do
  if [[ -d "$profile" ]]; then
    rmrf \
      "$profile"/Default/Service\ Worker/CacheStorage/* \
      "$profile"/Default/Service\ Worker/ScriptCache/* \
      "$profile"/Default/DawnWebGPUCache/* \
      "$profile"/Default/DawnGraphiteCache/* \
      "$profile"/Default/GrShaderCache/* \
      "$profile"/Default/ShaderCache/* \
      "$profile"/Default/BrowserMetrics/* \
      "$profile"/Default/Cache/* \
      "$profile"/Default/Code\ Cache/* \
      "$profile"/Default/GPUCache/* \
      "$profile"/Crashpad/* \
      "$profile"/component_crx_cache/* \
      "$profile"/extensions_crx_cache/*
  fi
done

# --- VS Code caches ---
rmrf \
  ~/Library/Application\ Support/Code/User/workspaceStorage/* \
  ~/Library/Application\ Support/Code/CachedExtensionVSIXs/* \
  ~/Library/Application\ Support/Code/Crashpad/* \
  ~/Library/Application\ Support/Code/CachedData/*

# --- Optional Android SDK cleanup ---
if [[ "$CLEAN_ANDROID" == true ]]; then
  SDK="$HOME/Library/Android/sdk"
  if [[ -d "$SDK/ndk" ]]; then
    newest_ndk=$(ls -1 "$SDK/ndk" 2>/dev/null | sort -V | tail -n 1)
    for dir in "$SDK/ndk"/*; do
      name=$(basename "$dir")
      if [[ -d "$dir" && "$name" != "$newest_ndk" ]]; then
        rmrf "$dir"
      fi
    done
  fi

  # Keep only android-36/google_apis
  if [[ -d "$SDK/system-images" ]]; then
    for api_dir in "$SDK/system-images"/*; do
      api=$(basename "$api_dir")
      if [[ "$api" != "android-36" ]]; then
        rmrf "$api_dir"
      else
        for variant_dir in "$api_dir"/*; do
          variant=$(basename "$variant_dir")
          if [[ "$variant" != "google_apis" ]]; then
            rmrf "$variant_dir"
          fi
        done
      fi
    done
  fi
fi

# --- Summary ---
echo ""
if [[ "$DRY_RUN" == true ]]; then
  echo "Dry-run complete. No files were removed."
else
  after=$(df -h /System/Volumes/Data | awk 'NR==2{print $5}')
  echo "Disk usage after cleanup: $after"
  echo "Cleanup complete."
fi
