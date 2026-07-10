---
name: quality-first-dev
description: Quality-first AI-assisted development workflow for tiny startup teams using GitHub Issues, git worktrees, Mini-PRDs, human-authored architecture, and conservative AI assistance. Use for normal/risky feature work, PRD drafting, architecture critique, worktree setup, implementation planning, PR review, and ship checks where quality must stay the same or improve.
---

# Quality-First Development

Use this skill when helping the team build or review non-trivial software changes under the team's quality-first AI-assisted methodology.

## Core Principle

**Quality is the floor; speed is optional upside.**

AI adoption is successful only if product and engineering quality stay the same or improve. Do not optimize for "10x output" at the expense of correctness, maintainability, security, product clarity, or architectural ownership.

## Non-Negotiable Boundaries

1. **Humans design the architecture and core algorithms.**
   - AI may propose alternatives, critique, compare trade-offs, identify risks, generate test vectors, and review.
   - AI must not own, silently redefine, or replace human architecture/core algorithm decisions.

2. **Humans own product judgment.**
   - AI may draft Mini-PRDs, clarify ambiguity, suggest acceptance criteria, and propose scope cuts.
   - A human PM/PO decides priority, scope, success criteria, and whether shipped behavior is acceptable.

3. **Humans hand-code or line-review important paths.**
   Important paths include:
   - architecture/module boundaries
   - core algorithms
   - domain invariants
   - auth and authorization
   - payments, billing, credits, ledgers
   - data deletion, privacy, PII, secrets
   - security-sensitive code
   - database migrations that can lose or corrupt data

4. **GitHub Issues are the product/process source of truth; GitHub is the code/quality source of truth.**
   - Normal/risky feature work should start from a GitHub Issue and end in a GitHub PR.

5. **Every issue is implemented in a dedicated git worktree.**
   - One issue = one worktree = one branch.
   - Worktree directory: `../worktrees/issue-NN-short-name`.
   - Branch name: `issue-NN/short-name`.
   - Example: `../worktrees/issue-42-add-billing-webhook` with branch `issue-42/add-billing-webhook`.

## Operating Model

```text
GitHub Issue
→ PM triage
→ Mini-PRD
→ human-authored architecture sketch / ADR-lite when needed
→ dedicated git worktree + branch (issue-NN/short-name)
→ bounded implementation slices
→ GitHub PR
→ CI/review/quality gate
→ merge
→ Issue closed
```

## Risk Classes

Classify work before deciding process weight.

| Risk | Examples | Required Process |
|---|---|---|
| `risk:tiny` | copy change, CSS tweak, simple UI polish | GitHub Issue optional; small PR preferred |
| `risk:normal` | settings page, onboarding flow, notification UI | GitHub Issue + Mini-PRD + dedicated worktree + PR |
| `risk:core` | auth, payments, permissions, billing, AI pipeline, user data | Mini-PRD + human architecture sketch + dedicated worktree + human review gate + PR |
| `risk:foundation` | database choice, event system, queue, multi-tenant model | ADR-lite before coding + dedicated worktree + human review gate + PR |

Suggested GitHub Issue AI labels:

```text
ai:free | ai:assist | ai:review-only | ai:human-only
```

Use `ai:human-only` or `ai:review-only` for architecture/core algorithms and critical code paths.

## Product Manager Hat

For each normal/risky feature, make sure someone explicitly wears the PM hat.

The PM hat owns **what and why**. The architecture/engineering hat owns **how**. The same person may wear both hats, but not at the same moment.

### PM Responsibilities

- Decide whether an idea is worth tracking.
- Prioritize the GitHub Issues backlog.
- Define the target user and problem.
- Write or approve the Mini-PRD.
- Define success criteria and acceptance criteria.
- Cut scope during implementation.
- Accept/reject shipped behavior from the product perspective.
- Create follow-up GitHub Issues after release.

### PM Checklist

```markdown
## PM Checklist
- [ ] What user/business problem are we solving?
- [ ] Why now?
- [ ] Who is the target user?
- [ ] What is explicitly out of scope?
- [ ] What does success look like?
- [ ] What are the acceptance criteria?
- [ ] What is the smallest shippable version?
- [ ] What should we measure or observe after release?
```

## Mini-PRD Template

Use this for normal/risky features. Keep it one page or less when possible. Put it in the GitHub Issue unless it needs a durable repo doc.

```markdown
# Mini-PRD: <Feature Name>

## Problem / Why Now
What user/business problem are we solving, and why does it matter now?

## Target User
Who experiences this problem?

## Desired Outcome
What should be true after this ships?

## Success Signal
Metric, user behavior, or qualitative signal that tells us it worked.

## Scope
- In scope:
- Out of scope:

## User Flow / Acceptance Criteria
- Given..., when..., then...
- Edge cases:
- Failure states:

## Risks
Security, privacy, data integrity, performance, UX, cost.

## Implementation Boundary
What must be hand-coded? What can AI generate or assist with?
```

For AI-heavy products, include evals, example prompts, and expected/undesired outputs.

## Human-Authored Architecture Sketch

For core/risky or foundational changes, require a human-authored design before implementation.

The architecture output should be concrete enough that implementation can proceed without AI inventing structure. It should usually include modules/components, entities/data, key flows, interfaces, and important decisions. It should not become a full enterprise design document.

### Architecture Design Output Checklist

For a normal feature, include the first 5–7 items. For core/foundation work, include all relevant items.

| Section | Include When | Purpose |
|---|---|---|
| Problem / context | Always | Why this design exists |
| Scope and non-goals | Always | Prevents accidental expansion |
| Module/component boundaries | Always for non-trivial work | Names the code areas and responsibilities |
| Domain entities / data model | When state/data changes | Defines tables, objects, ownership, lifecycle |
| API/contracts/events | When modules/services interact | Prevents hidden interface assumptions |
| Main flows / sequence | When behavior spans multiple steps | Shows who calls whom and in what order |
| Core algorithms / invariants | When correctness matters | Human-authored algorithm, constraints, edge cases |
| Failure modes | Risky/core work | Retries, partial failure, rollback, idempotency |
| Security/privacy | Risky/core work | Auth, permissions, PII, secrets, auditability |
| Migration/rollout plan | Data/foundation changes | Safe rollout, rollback, compatibility |
| Alternatives/trade-offs | Core/foundation work | Records why this design won |
| Test strategy | Always for risky work | Unit/integration/e2e/eval coverage expectations |
| AI boundary | Always under this methodology | What AI may propose/generate vs what humans own |

```markdown
# Architecture Sketch: <Feature Name>

## Current Context
Relevant existing modules, data models, APIs, jobs, integrations.

## Human-Authored Proposed Design
Short explanation of the approach. This section is written by the human owner, not generated by AI.

## AI Proposals / Critique
Optional: alternatives, risks, edge cases, or simplifications proposed by AI. These are inputs to human judgment, not accepted design by default.

## Data / State Changes
Tables, migrations, indexes, ownership, lifecycle, retention.

## API / Interface Changes
Endpoints, contracts, events, background jobs, external integrations.

## Failure Modes
What happens on timeout, retry, partial failure, duplicate request, rollback?

## Security / Privacy
Auth, authorization, input validation, secrets, PII, audit logs.

## Hand-Code vs AI-Assist Boundary
Human designs and hand-codes:
- architecture and module boundaries
- core algorithms
- domain invariants
- auth/permission checks
- payment/data-integrity paths
- migrations that can lose data

AI may propose/review:
- architecture alternatives and trade-offs
- algorithm approaches, edge cases, and test vectors
- security/privacy failure modes

AI may implement with human review:
- UI scaffolding
- boilerplate wiring
- tests from acceptance criteria
- docs/comments
- refactor suggestions
- non-critical admin tooling

## Alternatives Considered
Option A / B and why we are choosing this now.
```

## Human Review Gate

Before coding a core/risky feature, verify:

- [ ] Problem is clear enough to know when to stop.
- [ ] Out-of-scope items are explicit.
- [ ] Architecture is human-authored and understood.
- [ ] Core algorithms are human-designed and assigned for hand-coding.
- [ ] Important invariants are named.
- [ ] Security/privacy/data risks are called out.
- [ ] Hand-coded vs AI-assisted boundary is clear.

For solo work, use a forced pause and ask AI to critique, but never let the same AI that proposed the plan approve it.

## Implementation Workflow

When asked to implement a normal/risky feature:

1. Confirm there is a GitHub Issue number or ask for one.
2. Classify risk: tiny / normal / core / foundation.
3. Ensure Mini-PRD exists for normal/risky work.
4. Ensure human-authored architecture sketch or ADR exists for core/foundation work.
5. **Create a dedicated worktree for the issue** (not optional for normal/risky/core/foundation):
   ```bash
   # From the repo root:
   git worktree add ../worktrees/issue-NN-short-name -b issue-NN/short-name
   cd ../worktrees/issue-NN-short-name
   ```
   The worktree directory and branch must use the issue number.
6. Work only inside that worktree — never in the main working tree.
7. Ask for or produce an implementation plan before code.
8. Do not redefine architecture or core algorithms.
9. Implement only bounded, non-critical slices unless the human explicitly asks for hand-coded core logic and will review it.
10. Review diffs; reject broad opportunistic changes.
11. Run tests/typecheck/lint/build/security checks where available.
12. Open or prepare a GitHub PR with the quality checklist.

## AI Assistance Modes

### Allowed by Default

- Requirement critique
- Acceptance criteria suggestions
- Edge case discovery
- Architecture critique, not ownership
- Alternative proposals, not decisions
- Test case generation
- UI scaffolding
- Boilerplate
- Docs/comments/changelog drafts
- PR review and quality checks
- Refactor suggestions

### Restricted / Human-Owned

- Architecture decisions
- Data model decisions
- Core algorithm design
- Auth/authorization logic
- Payment/billing/ledger logic
- Data deletion and privacy-sensitive flows
- Destructive migrations
- Security boundary changes

For restricted areas, AI may provide critique, tests, threat models, or review comments, but humans must design and hand-code or line-review.

## GitHub PR Template Guidance

When reviewing or drafting PR descriptions, include:

```markdown
## Issue
- Closes #NN

## What changed
-

## Product / PRD
- Mini-PRD is in GitHub Issue: yes/no
- Acceptance criteria covered: yes/no

## Architecture / Risk
- Risk class: tiny / normal / core / foundation
- ADR or architecture sketch linked: yes/no/not needed

## Human Design Boundary
- Architecture designed by human: yes/no/not applicable
- Core algorithms designed by human: yes/no/not applicable
- Core algorithms hand-coded or line-reviewed by human: yes/no/not applicable

## AI Usage Boundary
- AI proposals considered:
- AI-assisted implementation parts:
- AI-generated code line-reviewed: yes/no/not applicable
- AI used for quality review? requirements / architecture / tests / security / refactor / none

## Quality Bar
- [ ] This PR maintains or improves existing quality
- [ ] AI changes were not accepted only for speed
- [ ] Important trade-offs are documented in Linear or ADR, if relevant

## Verification
- [ ] Tests pass
- [ ] Typecheck/lint/build pass
- [ ] Manual happy path checked
- [ ] Failure path checked
- [ ] Auth/permission checks reviewed, if relevant
- [ ] Data migration/rollback considered, if relevant
- [ ] No broad unrelated AI changes included
```

## How to Respond in This Skill

When the user asks for help under this methodology:

1. Be concise and process-light.
2. Ask for the GitHub Issue number if missing and the work is meaningful.
3. Classify risk before recommending workflow.
4. Separate PM questions from architecture questions.
5. Never present AI-generated architecture/core algorithms as final; present them as proposals for human decision.
6. Prefer checklists, templates, and concrete next actions.
7. Preserve the quality-first framing: same-or-better quality, not maximum velocity.
8. If coding, use small bounded edits and keep critical logic human-owned.

## Quick Commands the User May Ask For

- "Triage #NN" → classify risk, PM gaps, AI boundary.
- "Draft Mini-PRD for #NN" → produce Mini-PRD for human editing.
- "Critique this architecture" → critique only; do not take ownership.
- "Start feature #NN" → create worktree and branch (`issue-NN/short-name`).
- "Implement safe slice" → implement non-critical bounded work only.
- "Review PR" → quality/security/test/scope review.
- "Ship check" → verify acceptance criteria, quality bar, and follow-ups.
