#!/usr/bin/env python3
"""
add_word.py – Add a new word to the Jack Barsky vocabulary database.

Usage:
    python3 add_word.py -w WORD [options]

Examples:
    python3 add_word.py -w "plausible deniability" \
        -d "The ability for a senior official to claim ignorance of actions done on their behalf." \
        -u "Used in politics and business when a leader structures decision-making so they cannot be proven to have known about wrongdoing." \
        -r "formal" \
        --everyday "yes" \
        -t "politics,vocabulary"
"""

import argparse
import json
import os
import uuid
from datetime import date

VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'vocabulary.json')

CATEGORIES = {0: "New", 1: "Learning", 2: "Familiar", 3: "Proficient", 4: "Mastered"}


def load_vocab():
    if not os.path.exists(VOCAB_FILE):
        return {"version": "1.0", "words": []}
    with open(VOCAB_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_vocab(vocab):
    os.makedirs(os.path.dirname(VOCAB_FILE), exist_ok=True)
    with open(VOCAB_FILE, 'w', encoding='utf-8') as f:
        json.dump(vocab, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description='Add a new word to the Jack Barsky vocabulary database.'
    )
    parser.add_argument('-w', '--word', required=True,
                        help='The word or phrase to add')
    parser.add_argument('-d', '--definition', default='',
                        help='Core definition of the word')
    parser.add_argument('-u', '--daily-usage', default='',
                        help='How the word is used in everyday life')
    parser.add_argument('-p', '--phonetic', default='',
                        help='IPA phonetic transcription (e.g., /ɪˈnækt/)')
    parser.add_argument('--other-senses', default='',
                        help='Other meanings (semicolon-separated), for reference only')
    parser.add_argument('-r', '--register', choices=['formal', 'informal', 'neutral'], default='neutral',
                        help='Formality: formal (academic/professional), informal (casual), or neutral')
    parser.add_argument('--everyday', choices=['yes', 'no'], default='no',
                        help='Is it commonly used in everyday life? (yes/no)')
    parser.add_argument('-t', '--tags', default='',
                        help='Comma-separated tags, e.g. "vocabulary,language,business"')
    args = parser.parse_args()

    vocab = load_vocab()

    # Duplicate check
    word_lower = args.word.lower().strip()
    for w in vocab['words']:
        if w['word'].lower() == word_lower:
            print(f"⚠️  '{args.word}' already exists  [{CATEGORIES[w['category']]}]")
            print(f"   Definition:  {w['definition']}")
            if w.get('daily_usage'):
                print(f"   Daily usage: {w['daily_usage'][:80]}...")
            return 1

    tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else []

    entry = {
        "id": str(uuid.uuid4()),
        "word": args.word.strip(),
        "phonetic": args.phonetic.strip(),
        "definition": args.definition.strip(),
        "daily_usage": args.daily_usage.strip(),
        "other_senses": [s.strip() for s in args.other_senses.split(';') if s.strip()] if args.other_senses else [],
        "register": args.register,
        "everyday_use": args.everyday == 'yes',
        "tags": tags,
        "category": 0,
        "consecutive_correct": 0,
        "total_reviews": 0,
        "correct_reviews": 0,
        "last_reviewed": None,
        "date_added": date.today().isoformat()
    }

    vocab['words'].append(entry)
    save_vocab(vocab)

    print(f"\n✅ Added  '{args.word}'  →  🆕 New")
    if args.phonetic:
        print(f"   Phonetic:      {args.phonetic}")
    print(f"   Definition:    {args.definition or '(none)'}  [PRIMARY SENSE]")
    if args.daily_usage:
        print(f"   Daily usage:   {args.daily_usage}")
    if args.other_senses:
        other = [s.strip() for s in args.other_senses.split(';') if s.strip()]
        print(f"   Other senses:  {' | '.join(other)}  [reference only]")
    print(f"   Register:      {args.register}")
    print(f"   Everyday:      {'yes' if args.everyday == 'yes' else 'no'}")
    if tags:
        print(f"   Tags:          {', '.join(tags)}")
    print(f"\n   Total words in database: {len(vocab['words'])}")


if __name__ == '__main__':
    raise SystemExit(main())
