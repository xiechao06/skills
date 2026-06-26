---
name: jack-barsky
description: Vocabulary builder with spaced repetition learning system. Add words from any source, run interactive 25-minute review sessions with grading, and track progress across 5 mastery categories. Build vocabulary methodically with daily usage examples and video context. Use when adding vocabulary, running learning sessions, or checking progress.
---

# Vocabulary Builder Skill

A spaced repetition vocabulary learning system. Add any word from any source, learn interactively with feedback, and track mastery progress.

**Methodology foundation:** Built on the Jack Barsky interview (Lex Fridman #301), but works with vocabulary from any source.

**Database:** [`data/vocabulary.json`](data/vocabulary.json)
**Scripts:** [`scripts/`](scripts/) directory

All scripts run via:

```bash
cd "$(dirname "$SKILL_PATH")"
python3 scripts/<script>.py [args]
```

---

## Feature 1 — Add a New Word

**Interactive workflow:** Ask the user for word senses, then fetch definitions from APIs, refine together, and save.

### Step 1 – Ask for the word

```
📝 What word would you like to add?
```

Wait for the user to provide a word or phrase.

### Step 2 – Fetch definition from APIs

Once they provide the word, automatically fetch definitions:

```bash
python3 scripts/fetch_definitions.py "word"
```

This queries **Free Dictionary API** for:
- Primary definition
- Multiple senses (curated to ~2-3 most common)
- Part of speech
- Example sentences
- Register classification

**Display the results to the user:**

```
🔍 Looking up '{word}'...

✨ Definition from Free Dictionary API:

Primary sense:
  To move swiftly.

Other senses:
  1. Act or instance of running...
  2. Act or instance of hurrying...

Example sentences:
  • I just got back from my morning run.
  • I need to make a run to the store.

Part of speech: verb
Register: neutral
```

### Step 3 – Ask the user for their understanding

Then ask them what they know about the word:

```
🤔 Before we finalize, what does '{word}' mean to you?
   (Don't worry if your definition isn't as polished as the API one.
    Tell me in your own words—we'll use API as a starting point.)
```

**Wait for their response.** They might:
- Agree with the API definition
- Provide additional context
- Disagree or refine part of it
- Share personal examples

### Step 4 – Refine and enhance together

Based on what they said:

1. **Confirm the primary sense** — is the API definition what they meant?
2. **Highlight the most everyday sense** — "The primary meaning most people use is..."
3. **Simplify if needed** — the API definition might be technical; suggest plainer language
4. **Add their examples** — if they provided better examples than the API
5. **Classify register** — formal, informal, or neutral (the API helps guide this)
6. **Note everyday use** — "This is very common" or "Less commonly used"
7. **Suggest tags** — topic categories for grouping

**Present the final refined summary:**

```
✨ Here's what we'll save:

  Word:          run
  Definition:    To move quickly by foot with both feet leaving the ground.
                 [PRIMARY SENSE from API + your confirmation]
  Daily usage:   "I run 5 miles every morning."
                 "She ran to catch the bus."
  Other senses:  to operate ("run a business")
                 to flow ("water runs downhill")
  Register:      neutral
  Everyday:      yes (very common)
  Tags:          vocabulary, movement

Does this look right? Any corrections? (yes / edit / skip)
```

### Step 5 – Confirm or iterate

If the user says:
- **"yes"** → Proceed to Step 6
- **"edit"** → Ask which field to correct, then refine again
- **"skip"** → Don't save, end the flow

### Step 6 – Run the save script

Once approved:

```bash
python3 scripts/add_word.py \
  --word "run" \
  --definition "To move quickly by foot with both feet leaving the ground." \
  --daily-usage "I run 5 miles every morning. / She ran to catch the bus." \
  --other-senses "to operate;to flow;a sequence" \
  --register "neutral" \
  --everyday "yes" \
  --tags "vocabulary,movement"
```

Confirm to the user:
```
✅ Added 'run' to your vocabulary!
   Total words: 8
```

### Useful reference commands

Once words are added, users can:

```bash
python3 scripts/fetch_definitions.py "word"  # Fetch definitions from Free Dictionary API
python3 scripts/list_words.py                 # all words
python3 scripts/list_words.py --tag vocabulary  # filter by tag
python3 scripts/list_words.py --category 1      # filter by category
```

---

## Feature 2 — 25-Minute Learning Session

### How to run a session

**Step 1 – Fetch words**
```bash
python3 scripts/next_words.py --limit 15
```
This returns JSON with up to 15 words prioritised by category (New first, then Learning, Familiar, Proficient). 15 words ≈ 25 minutes at ~1.5 min/word.

**Step 2 – Announce the session**
Tell the user:
```
🎓 Starting a 25-minute learning session · {N} words queued
   Low-category words come first. Take your time!
──────────────────────────────────────────────────
```

**Step 3 – For each word, run this exact loop:**

1. **Present the word:**
   ```
   ── Word {i}/{N} ── [{category_name}] ─────────────────
   💬  {word}
   ─────────────────────────────────────────────────────
   What does this mean? Give me your definition AND at
   least one example sentence.
   ```

2. **Wait for user response.**

3. **Judge the response** against the **primary sense only**:
   - `definition` — did they explain the most frequent, everyday meaning?
   - `daily_usage` — did they provide a valid example sentence for that sense?
   - Other senses are bonus context but NOT required to pass

   **Grading rubric:**
   | Grade | Criteria |
   |-------|----------|
   | ✅ 3 — Correct | Primary meaning is accurate AND at least one valid example sentence |
   | 🔶 2 — Partial | Primary meaning mostly right but vague, or missing example sentence; or explained a secondary sense |
   | ❌ 1 — Wrong | Primary meaning wrong, confused, or "I don't know" |

4. **Give feedback:**
   - State the grade clearly
   - Quote the **primary sense** definition
   - Quote a valid example sentence
   - If the word has other senses, mention them as bonus context: *"Other meanings: to operate, to manage, to flow"*
   - If partial/wrong, briefly explain what was missing or incorrect
   - Keep feedback warm and encouraging

5. **Record the result:**
   ```bash
   python3 scripts/update_word.py --word "{word}" -g {grade}
   ```
   Show the output (category change or streak progress).

6. **Check time:** After every 5 words say:
   ```
   ⏱  ~{elapsed} min elapsed · {remaining} words left
   ```
   If the user wants to stop early, respect that.

**Step 4 – End of session**
When all words are done (or user calls time):
```
🏁  Session complete!
```
Then run stats:
```bash
python3 scripts/stats.py
```

### Session principles
- **One word at a time** — never reveal the next word early.
- **No hints** unless asked. If the user says "hint please," give the first letter or the definition, but reduce max grade to 2.
- **Positive tone** — celebrate every category advance.
- **Do not skip** grading steps; every word must be recorded.

---

## Feature 3 — Statistics

Show the learning dashboard at any time:

```bash
python3 scripts/stats.py
```

This displays:
- Total words, ever-reviewed count, total review sessions, overall accuracy
- **Category breakdown** with progress bars:
  - 🆕 **New** — added, never reviewed
  - 📖 **Learning** — reviewed but still making mistakes
  - 🔄 **Familiar** — getting it right, not yet consistent
  - 💪 **Proficient** — consistently correct, almost mastered
  - ⭐ **Mastered** — fully learned

- Recently reviewed words

### Advancement thresholds (inside update_word.py)

| From | To | Consecutive correct needed |
|------|----|---------------------------|
| 🆕 New | 📖 Learning | 1 (any review) |
| 📖 Learning | 🔄 Familiar | 2 |
| 🔄 Familiar | 💪 Proficient | 3 |
| 💪 Proficient | ⭐ Mastered | 5 |
| Any wrong (grade 1) | 📖 Learning | — (drops back) |

---

## Key Principles

**For adding words:**
- Always prioritize the most common, everyday sense
- Other meanings are reference context, not required for mastery
- Example sentences are essential to ground meaning
- Register and frequency matter for context

**For learning sessions:**
- Grade only the primary sense — secondary senses are bonus
- A correct explanation + valid example = mastery
- Build confidence; celebrate progress

**For long-term learning:**
- Spaced repetition (New → Learning → Familiar → Proficient → Mastered)
- Wrong answers drop back to Learning; consistent correct answers advance
- Regular review sessions maintain and build vocabulary steadily
