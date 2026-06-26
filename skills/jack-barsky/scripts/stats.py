#!/usr/bin/env python3
"""
stats.py – Show learning statistics and category breakdown.

Usage:
    python3 stats.py
    python3 stats.py --json
"""

import argparse
import json
import os
from collections import Counter

VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'vocabulary.json')

CATEGORIES = {0: "New", 1: "Learning", 2: "Familiar", 3: "Proficient", 4: "Mastered"}
CAT_EMOJI  = {0: "🆕", 1: "📖", 2: "🔄", 3: "💪", 4: "⭐"}
WIDTH = 46   # inner box width


def load_vocab():
    if not os.path.exists(VOCAB_FILE):
        return {"version": "1.0", "words": []}
    with open(VOCAB_FILE, encoding='utf-8') as f:
        return json.load(f)


def bar(count, total, width=18):
    if total == 0:
        return "─" * width
    filled = round(count / total * width)
    return "█" * filled + "░" * (width - filled)


def box_line(content='', width=WIDTH):
    """Pad content to fill a box line: ║ content ║"""
    return f"║ {content:<{width}} ║"


def main():
    parser = argparse.ArgumentParser(description='Show vocabulary learning statistics.')
    parser.add_argument('--json', action='store_true', help='Output raw JSON')
    args = parser.parse_args()

    vocab = load_vocab()
    words = vocab.get('words', [])

    if not words:
        print("\n  No words yet — add some with add_word.py!\n")
        return 0

    total         = len(words)
    counts        = Counter(w.get('category', 0) for w in words)
    total_reviews = sum(w.get('total_reviews', 0)  for w in words)
    total_correct = sum(w.get('correct_reviews', 0) for w in words)
    accuracy      = (total_correct / total_reviews * 100) if total_reviews > 0 else 0
    ever_reviewed = sum(1 for w in words if w.get('total_reviews', 0) > 0)
    mastered_pct  = counts[4] / total * 100 if total > 0 else 0

    if args.json:
        data = {
            "total_words":    total,
            "ever_reviewed":  ever_reviewed,
            "total_reviews":  total_reviews,
            "accuracy_pct":   round(accuracy, 1),
            "mastered_pct":   round(mastered_pct, 1),
            "categories": {CATEGORIES[i]: counts[i] for i in range(5)},
        }
        print(json.dumps(data, indent=2))
        return 0

    # ── Recent activity ──────────────────────────────────────────────────────
    reviewed = sorted(
        [w for w in words if w.get('last_reviewed')],
        key=lambda w: w['last_reviewed'],
        reverse=True
    )[:5]

    # ── Box drawing ──────────────────────────────────────────────────────────
    sep = "╠" + "═" * (WIDTH + 2) + "╣"
    top = "╔" + "═" * (WIDTH + 2) + "╗"
    bot = "╚" + "═" * (WIDTH + 2) + "╝"

    title = "Jack Barsky Vocabulary  ·  Stats"
    print(f"\n{top}")
    print(box_line(f"{title:^{WIDTH}}"))
    print(sep)

    print(box_line(f"Total words    {total:>4}"))
    print(box_line(f"Ever reviewed  {ever_reviewed:>4}  /  {total}"))
    print(box_line(f"Total reviews  {total_reviews:>4}"))
    print(box_line(f"Accuracy       {accuracy:>6.1f}%"))
    print(box_line(f"Mastered       {mastered_pct:>6.1f}%  of all words"))
    print(sep)

    # ── Category bars ────────────────────────────────────────────────────────
    print(box_line("Categories"))
    print(box_line())
    for cat_id in range(5):
        count = counts[cat_id]
        b     = bar(count, total)
        pct   = count / total * 100 if total > 0 else 0
        label = f"{CAT_EMOJI[cat_id]} {CATEGORIES[cat_id]:<10}"
        line  = f"{label} [{b}] {count:>3}  {pct:>4.0f}%"
        print(box_line(line))

    # ── Recent ───────────────────────────────────────────────────────────────
    if reviewed:
        print(sep)
        print(box_line("Recently reviewed"))
        print(box_line())
        for w in reviewed:
            cat   = w.get('category', 0)
            label = f"{CAT_EMOJI[cat]} {w['word'][:30]:<30} {w['last_reviewed']}"
            print(box_line(label))

    print(bot)
    print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
