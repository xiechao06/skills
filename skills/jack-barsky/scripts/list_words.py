#!/usr/bin/env python3
"""
list_words.py – List vocabulary words with optional filters.

Usage:
    python3 list_words.py
    python3 list_words.py --tag tradecraft
    python3 list_words.py --category 1
    python3 list_words.py --format json
"""

import argparse
import json
import os

VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'vocabulary.json')

CATEGORIES = {0: "New", 1: "Learning", 2: "Familiar", 3: "Proficient", 4: "Mastered"}
CAT_EMOJI  = {0: "🆕", 1: "📖", 2: "🔄", 3: "💪", 4: "⭐"}


def load_vocab():
    if not os.path.exists(VOCAB_FILE):
        return {"version": "1.0", "words": []}
    with open(VOCAB_FILE, encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='List vocabulary words.')
    parser.add_argument('--tag',      help='Filter by tag')
    parser.add_argument('--category', type=int, choices=[0, 1, 2, 3, 4],
                        help='0=New  1=Learning  2=Familiar  3=Proficient  4=Mastered')
    parser.add_argument('--limit',    type=int, help='Max words to show')
    parser.add_argument('--format',   choices=['table', 'json'], default='table')
    args = parser.parse_args()

    vocab = load_vocab()
    words = vocab.get('words', [])

    if args.tag:
        words = [w for w in words if args.tag in w.get('tags', [])]
    if args.category is not None:
        words = [w for w in words if w.get('category', 0) == args.category]
    if args.limit:
        words = words[:args.limit]

    if not words:
        print("No words found.")
        return 0

    if args.format == 'json':
        print(json.dumps(words, indent=2, ensure_ascii=False))
        return 0

    # ── Table ──────────────────────────────────────────────────────────────
    header = f"{'#':<4}{'WORD':<28}{'STATUS':<16}{'REVIEWS':<9}{'ACCURACY':<10}{'LAST REVIEWED'}"
    print(f"\n{header}")
    print("─" * 80)

    for i, w in enumerate(words, 1):
        cat     = w.get('category', 0)
        status  = f"{CAT_EMOJI[cat]} {CATEGORIES[cat]}"
        reviews = w.get('total_reviews', 0)
        correct = w.get('correct_reviews', 0)
        acc     = f"{correct/reviews*100:.0f}%" if reviews > 0 else "—"
        last    = w.get('last_reviewed') or "—"
        word    = w['word'][:27]
        print(f"{i:<4}{word:<28}{status:<16}{reviews:<9}{acc:<10}{last}")

    print("─" * 80)
    print(f"  {len(words)} word(s) shown\n")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
