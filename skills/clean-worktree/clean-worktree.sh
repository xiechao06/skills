#!/usr/bin/env bash
set -euo pipefail

# ── clean-worktree.sh ───────────────────────────────────────────────
# Clean up a git worktree after PR merge: delete remote/local branch,
# then print the steps for the agent to remove the worktree and sync.
#
# Usage: bash clean-worktree.sh [target-branch] [--force]
#   target-branch  Branch to switch back to (default: main)
#   --force        Skip the "is branch merged?" safety check
# ─────────────────────────────────────────────────────────────────────

TARGET_BRANCH="${1:-main}"
FORCE=false
if [[ "${2:-}" == "--force" ]] || [[ "${1:-}" == "--force" ]]; then
  FORCE=true
  [[ "$1" == "--force" ]] && TARGET_BRANCH="main"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
div()   { echo "──────────────────────────────────────────────────"; }

div
echo "  clean-worktree"
div

# ── Detect current context ──────────────────────────────────────────
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || {
  err "Not inside a git repository."
  exit 1
}

# Determine main repo root (works for both worktrees and main repos)
GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null) || {
  err "Cannot determine git common directory."
  exit 1
}

if [[ "$GIT_COMMON_DIR" == ".git" ]]; then
  # We are in the main working tree
  MAIN_REPO=$(git rev-parse --show-toplevel)
  IS_WORKTREE=false
else
  # We are likely in a worktree; git-common-dir looks like:
  #   /path/to/main/.git/worktrees/name
  #   /path/to/main/.git (for bare-style setups)
  if [[ "$GIT_COMMON_DIR" == *"/.git/worktrees/"* ]]; then
    MAIN_REPO="${GIT_COMMON_DIR%/.git/worktrees/*}"
    IS_WORKTREE=true
  else
    # fallback
    MAIN_REPO=$(git rev-parse --show-toplevel)
    IS_WORKTREE=false
  fi
fi

CURRENT_WORKTREE=$(git rev-parse --show-toplevel)

info "Current branch:     $CURRENT_BRANCH"
if $IS_WORKTREE; then
  info "Current worktree:   $CURRENT_WORKTREE"
fi
info "Main repo:          $MAIN_REPO"
info "Target branch:      $TARGET_BRANCH"
echo ""

# ── Safety: don't destroy the target branch ─────────────────────────
if [[ "$CURRENT_BRANCH" == "$TARGET_BRANCH" ]]; then
  warn "Already on $TARGET_BRANCH. Nothing to clean."
  warn "If you meant to clean a different worktree, run this from that worktree."
  exit 0
fi

# ── Fetch latest ────────────────────────────────────────────────────
step "Fetching latest from origin..."
git fetch origin --prune 2>&1 | tail -1 || warn "Fetch had issues; continuing."

# ── Check if remote branch exists ──────────────────────────────────
REMOTE_EXISTS=false
if git ls-remote --exit-code --heads origin "$CURRENT_BRANCH" > /dev/null 2>&1; then
  REMOTE_EXISTS=true
  info "Remote branch origin/$CURRENT_BRANCH exists."
else
  warn "Remote branch origin/$CURRENT_BRANCH does not exist (already deleted?)."
fi

# ── Check if branch is merged ──────────────────────────────────────
if $FORCE; then
  warn "--force used: skipping merge-status check."
else
  if $REMOTE_EXISTS; then
    # We need the target branch's remote tracking ref
    if git rev-parse --verify "origin/$TARGET_BRANCH" > /dev/null 2>&1; then
      if git branch -r --merged "origin/$TARGET_BRANCH" 2>/dev/null | grep -q "origin/$CURRENT_BRANCH"; then
        info "Branch origin/$CURRENT_BRANCH is merged into origin/$TARGET_BRANCH."
      else
        warn "Branch origin/$CURRENT_BRANCH does NOT appear to be merged into origin/$TARGET_BRANCH."
        warn "If the PR is actually merged, re-run with --force."
        warn "Or verify: git branch -r --merged origin/$TARGET_BRANCH | grep $CURRENT_BRANCH"
        exit 1
      fi
    else
      warn "No remote tracking for origin/$TARGET_BRANCH. Skipping merge check."
      warn "If unsure, abort and fetch first. Use --force to skip."
      exit 1
    fi
  fi
fi

# ── Delete remote branch ───────────────────────────────────────────
if $REMOTE_EXISTS; then
  step "Deleting remote branch origin/$CURRENT_BRANCH..."
  if git push origin --delete "$CURRENT_BRANCH" 2>&1; then
    info "Remote branch deleted."
  else
    err "Failed to delete remote branch."
    exit 1
  fi
fi

# ── Delete local branch from main repo ──────────────────────────────
step "Deleting local branch '$CURRENT_BRANCH' from main repo..."
if git -C "$MAIN_REPO" branch -D "$CURRENT_BRANCH" 2>&1; then
  info "Local branch deleted."
else
  warn "Local branch may have already been deleted."
fi

# ── Print agent instructions ───────────────────────────────────────
echo ""
div
echo -e "  ${GREEN}Script complete.${NC} The agent must now finish cleanup:"
div
echo ""
echo "  1. Switch to main repo:"
echo -e "     ${CYAN}cd \"$MAIN_REPO\"${NC}"
echo ""

if $IS_WORKTREE; then
  echo "  2. Remove the worktree (you are currently in it):"
  echo -e "     ${CYAN}git worktree remove \"$CURRENT_WORKTREE\"${NC}"
  echo "     (use --force if the worktree has changes you are sure to discard)"
  echo ""
fi

echo "  3. Checkout target branch:"
echo -e "     ${CYAN}git checkout \"$TARGET_BRANCH\"${NC}"
echo ""

echo "  4. Pull latest:"
echo -e "     ${CYAN}git pull origin \"$TARGET_BRANCH\"${NC}"
echo ""

echo "  5. Verify:"
echo -e "     ${CYAN}git worktree list${NC}"
echo ""

div
info "Done. Handing off to agent for final steps."
