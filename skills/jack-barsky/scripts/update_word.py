#!/usr/bin/env python3
"""
update_word.py – Record a review result and update a word's category.

Grading scale:
    1 = Wrong   → consecutive_correct reset to 0; drop to Learning (cat 1)
    2 = Partial → consecutive_correct reset to 0; no category change
    3 = Correct → consecutive_correct +1; advance category if threshold met

Advancement thresholds (consecutive correct needed):
    New  (0) → Learning  (1) : 1
    Learning (1) → Familiar  (2) : 2
    Familiar (2) → Proficient(3) : 3
    Proficient(3)→ Mastered  (4) : 5

Usage:
    python3 update_word.py --word "dead drop"  -g 3
    python3 update_word.py --id  <uuid>         -g 1
"""

import argparse
import json
import os
from datetime import date

VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'vocabulary.json')

CATEGORIES   = {0: "New", 1: "Learning", 2: "Familiar", 3: "Proficient", 4: "Mastered"}
CAT_EMOJI    = {0: "🆕",  1: "📖",       2: "🔄",       3: "💪",         4: "⭐"}
GRADE_LABEL  = {1: "❌ Wrong", 2: "🔶 Partial", 3: "✅ Correct"}

# consecutive correct needed to advance from category N
ADVANCE_THRESHOLD = {0: 1, 1: 2, 2: 3, 3: 5, 4: 999}


def load_vocab():
    if not os.path.exists(VOCAB_FILE):
        return {"version": "1.0", "words": []}
    with open(VOCAB_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_vocab(vocab):
    with open(VOCAB_FILE, 'w', encoding='utf-8') as f:
        json.dump(vocab, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description='Record a review result for a word.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--id',   help='Word UUID')
    group.add_argument('--word', help='Word text (case-insensitive)')
    parser.add_argument('-g', '--grade', type=int, choices=[1, 2, 3], required=True,
                        help='1=wrong  2=partial  3=correct')
    args = parser.parse_args()

    vocab = load_vocab()

    # ── Find entry ──────────────────────────────────────────────────────────
    entry = None
    for w in vocab['words']:
        if args.id   and w['id']           == args.id:
            entry = w; break
        if args.word and w['word'].lower() == args.word.lower().strip():
            entry = w; break

    if not entry:
        print(f"❌ Word not found: {args.id or args.word}")
        return 1

    old_cat         = entry.get('category', 0)
    old_consecutive = entry.get('consecutive_correct', 0)

    # ── Update counters ─────────────────────────────────────────────────────
    entry['total_reviews'] = entry.get('total_reviews', 0) + 1
    entry['last_reviewed'] = date.today().isoformat()

    if args.grade == 1:          # Wrong
        entry['consecutive_correct'] = 0
        if old_cat == 0:
            entry['category'] = 1   # New always moves to Learning after first review
        elif old_cat > 1:
            entry['category'] = 1   # Drop back to Learning

    elif args.grade == 2:        # Partial
        entry['consecutive_correct'] = 0
        if old_cat == 0:
            entry['category'] = 1   # Out of New after any review

    else:                        # Correct
        entry['correct_reviews']    = entry.get('correct_reviews', 0) + 1
        entry['consecutive_correct'] = old_consecutive + 1
        threshold = ADVANCE_THRESHOLD.get(old_cat, 999)
        if entry['consecutive_correct'] >= threshold and old_cat < 4:
            entry['category']            = old_cat + 1
            entry['consecutive_correct'] = 0   # reset streak after advancing
        elif old_cat == 0:
            entry['category'] = 1               # New → Learning

    new_cat = entry['category']
    save_vocab(vocab)

    # ── Output ──────────────────────────────────────────────────────────────
    print(f"\n{GRADE_LABEL[args.grade]}  ·  '{entry['word']}'")
    if new_cat != old_cat:
        print(f"  {CAT_EMOJI[old_cat]} {CATEGORIES[old_cat]}  →  {CAT_EMOJI[new_cat]} {CATEGORIES[new_cat]}  🎉")
    else:
        streak = entry['consecutive_correct']
        needed = ADVANCE_THRESHOLD.get(new_cat, 999)
        if new_cat < 4:
            print(f"  {CAT_EMOJI[new_cat]} {CATEGORIES[new_cat]}  (streak {streak}/{needed} to advance)")
        else:
            print(f"  {CAT_EMOJI[new_cat]} {CATEGORIES[new_cat]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
