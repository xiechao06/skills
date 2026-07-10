---
description: Implement a GitHub issue end-to-end in a dedicated worktree (code, subagent review, PR)
---

Implement GitHub issue **#$1** in this repo, following `AGENTS.md` conventions. The issue must
be implemented in a dedicated git worktree, then reviewed by a subagent before opening the
pull request.

Extra instructions from the caller (may be empty): ${@:2}

## Steps

1. **Read the issue.**
   Use the `gh-axi` skill (`npx -y gh-axi issue view $1`) to fetch the issue title, body,
   labels, and any linked discussion/comments. Check whether this issue depends on other
   issues, and make sure those dependencies are finished before you start. Note any relevant
   packages, modules, or areas because they affect where you make changes and how you title the
   commit/PR.

2. **Set up a dedicated worktree before coding.**
   Per `AGENTS.md`, issue implementation must happen in a dedicated worktree named with the
   issue number. Create branch `issue-$1/short-description` (short-description derived from the
   issue title) in a new worktree, then use `switch_worktree` to relocate this session there
   before writing any code. Do not implement the issue in the main working tree. You should
   switch to worktree automatically. Skip this step only if the session is already correctly
   positioned in that worktree.

3. **Implement the change.**
   Follow the architecture rules and coding standards in `AGENTS.md` and any repo-specific
   conventions it points to:
   - Respect layer boundaries and ownership rules in the codebase.
   - Keep changes consistent with existing threading, naming, error-handling, and documentation
     patterns.
   - Regenerate generated artifacts or bindings if the change touches an interface that requires
     it.
   - Write or update tests for the change.
   - If the issue touches a critical or sensitive path (for example auth, permissions, payments,
     data deletion, migrations, privacy, security, domain invariants, or core algorithms), and
     the repository requires a design note or architecture sketch first, stop and ask the user
     before writing code.

4. **Commit.**
   Use the commit format from `AGENTS.md`:
   ```
   [area] Short description

   Details...

   - Change 1
   - Change 2

   Closes #$1
   ```
   Use a concise area/module label that matches the code you changed.

5. **Subagent review — do this before opening the PR.**
   Invoke the `reviewer` subagent (via the `subagent` tool) against the diff you just produced
   (e.g. `git diff main...HEAD` or the equivalent range). Ask it to check correctness, adherence
   to `AGENTS.md` conventions, test coverage, and anything risky.
   - If the reviewer raises high-confidence issues, fix them and re-commit before continuing.
   - Do not skip this step, and do not act as your own reviewer.

6. **Push and open the PR.**
   Push the branch, then use the `gh-axi` skill to create the pull request:
   - Title mirrors the commit's `[area] Short description` line.
   - Body summarizes the change, lists the modules/areas touched, notes the reviewer subagent's
     findings and how they were addressed, and ends with `Closes #$1`.
   - Do not merge — GitHub PR checks and human review are required before merge per team
     policy. Report the PR URL back to the user when done.

Work through these steps yourself; only step 5 is delegated to a subagent.
