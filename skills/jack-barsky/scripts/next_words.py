#!/usr/bin/env python3
"""
next_words.py – Return the next batch of words for a review session (JSON).

Priority order: New → Learning → Familiar → Proficient.
Mastered words are excluded unless --include-mastered is passed.

Usage:
    python3 next_words.py --limit 15
    python3 next_words.py --limit 20 --include-mastered
"""

import argparse
import json
import os

VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'vocabulary.json')

CATEGORIES = {0: "New", 1: "Learning", 2: "Familiar", 3: "Proficient", 4: "Mastered"}


def load_vocab():
    if not os.path.exists(VOCAB_FILE):
        return {"version": "1.0", "words": []}
    with open(VOCAB_FILE, encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Get next words for a review session.')
    parser.add_argument('--limit',           type=int, default=15,
                        help='Max words to return (default 15, ~25 min session)')
    parser.add_argument('--include-mastered', action='store_true',
                        help='Include Mastered words in the session')
    args = parser.parse_args()

    vocab = load_vocab()
    words = vocab.get('words', [])

    if not args.include_mastered:
        words = [w for w in words if w.get('category', 0) < 4]

    # Sort: lower category first (highest priority), then by last_reviewed ascending
    # (oldest reviewed first within same category)
    words.sort(key=lambda w: (
        w.get('category', 0),
        w.get('last_reviewed') or '0000-00-00'
    ))

    words = words[:args.limit]

    if not words:
        print(json.dumps({"error": "No words available for review.", "words": []}))
        return 0

    output = []
    for w in words:
        output.append({
            "id":                 w['id'],
            "word":               w['word'],
            "phonetic":           w.get('phonetic', ''),
            "definition":         w.get('definition', ''),
            "daily_usage":        w.get('daily_usage', ''),
            "other_senses":       w.get('other_senses', []),
            "register":           w.get('register', 'neutral'),
            "everyday_use":       w.get('everyday_use', False),
            "tags":               w.get('tags', []),
            "category":           w.get('category', 0),
            "category_name":      CATEGORIES[w.get('category', 0)],
            "consecutive_correct": w.get('consecutive_correct', 0),
            "total_reviews":      w.get('total_reviews', 0),
            "correct_reviews":    w.get('correct_reviews', 0),
        })

    print(json.dumps({"words": output, "count": len(output)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
