---
name: write-lean-spec
description: Draft or revise a concise, testable feature specification
  when a user describes a new feature or a change in business behavior.
---

# Write a lean specification

Turn the user's intent into a small, reviewable behavioral contract.
Do not write implementation code.

## Workflow

1. Read relevant existing specs and project conventions.
2. Identify missing decisions that materially change behavior.
3. Ask up to three focused questions at a time when necessary.
   Never silently invent business rules.
4. Draft or update the spec using the structure below.
5. Check for ambiguity, contradictions, and untestable requirements.
6. Present the draft and unresolved questions for approval.
   Do not treat a draft as approved.

## Output

### Purpose
Who needs this, what it does, and why. One short paragraph.

### Scope
What is included and explicitly excluded.

### Rules
Numbered, observable requirements.
Include permissions, state changes, and failure behavior where relevant.

### Examples
Three to five concrete input/action → expected outcome examples.
Include a failure or boundary case.

### Open questions
Unresolved decisions. Write "None" if there are none.

## Constraints

- Target one page for a small feature.
- Omit irrelevant sections; do not fill a template for its own sake.
- Reference existing rules instead of duplicating them.
- Separate required behavior from implementation choices.
- Expand only when complexity or risk justifies it.
- When revising a spec, summarize what changed and why.
