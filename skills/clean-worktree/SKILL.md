---
name: clean-worktree
description: Clean up a git worktree and its branch after a pull request is merged — delete the remote branch, the local branch, remove the worktree directory, then switch back to the target branch (default main) and sync. Use when a PR is merged and the feature branch + worktree are no longer needed, or when user mentions cleaning up worktrees, removing stale branches, or post-merge cleanup.
---

# clean-worktree

Clean up a git worktree after the associated pull request has been merged. Deletes the remote branch, local branch, removes the worktree, then switches the main repository to the target branch and pulls latest.

## When to use

- User says "clean up this worktree", "PR was merged, clean up", "delete the branch and worktree"
- After merging a PR created from a git worktree (e.g. following the quality-first-dev workflow)
- When a feature branch is no longer needed and the worktree should be removed
- User wants to switch back to main and sync after completing work in a worktree

## How it works

The script does the heavy lifting. The agent coordinates the workflow because removing the worktree requires leaving the directory.

### Script: `clean-worktree.sh`

```
Usage: bash clean-worktree.sh [target-branch] [--force]

  target-branch  Branch to switch back to (default: main)
  --force        Skip the "is branch merged?" safety check
```

The script, with agent help:

1. Detects the current branch and worktree
2. Fetches latest from origin
3. Verifies the branch is merged into the target branch (unless `--force`)
4. Deletes the remote branch (`git push origin --delete <branch>`)
5. Deletes the local branch from the main repo (`git branch -D <branch>`)
6. Reports the paths the agent needs to act on

The agent then:

7. Switches to the main repository directory
8. Removes the worktree (`git worktree remove <path>`)
9. Checks out the target branch (`git checkout <target-branch>`)
10. Pulls latest (`git pull origin <target-branch>`)

## Agent workflow

When the user asks to clean up a worktree:

1. **Confirm** the PR is merged. Ask the user if unsure.
2. **Run the script** from the worktree directory:
   ```bash
   cd skills/clean-worktree
   bash ./clean-worktree.sh [target-branch] [--force]
   ```
   If the user is already in a skills project, resolve the path relative to the project root.
3. **Follow the script's output** — it will print the main repo path, worktree path, and the commands the agent needs to run next.
4. **Complete the cleanup** by executing the printed commands:
   - `cd <main-repo>`
   - `git worktree remove <worktree-path>`
   - `git checkout <target-branch>`
   - `git pull origin <target-branch>`
5. **Verify** with `git worktree list` that only the main worktree remains.

## Example

```
User: "PR #42 is merged. Clean up the worktree."
Agent: 
  1. Runs: bash skills/clean-worktree/clean-worktree.sh main
  2. Script deletes remote branch origin/issue-42/add-settings
  3. Agent completes: cd main-repo, git worktree remove ../worktrees/issue-42-add-settings,
     git checkout main, git pull origin main
  4. Confirms: "Worktree cleaned. Now on main, up to date."
```

## Safety

- The script checks that the branch has been merged into the target's remote tracking branch before deleting. Use `--force` only when you are certain.
- Remote branch deletion can be recovered via GitHub's recently-deleted branches within 90 days.
- The worktree removal is non-destructive; uncommitted changes in the worktree will cause `git worktree remove` to fail (add `--force` to override, but only when you've verified nothing important is unsaved).
