#!/usr/bin/env python3
"""
Fetch word definitions from free public APIs.
Uses Free Dictionary API (freedictionary.dev) as primary source.
Includes IPA phonetic transcription when available.
"""

import json
import sys
import urllib.request
import urllib.error
from typing import Dict, List, Optional

def get_free_dictionary(word: str) -> Optional[Dict]:
    """
    Fetch definition from Free Dictionary API (freedictionary.dev).
    Returns comprehensive data with phonetics (IPA), parts of speech, definitions, examples.
    No auth required, generous free tier.
    """
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
        req = urllib.request.Request(url, headers={'User-Agent': 'VocabularyBuilder/1.0'})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            if isinstance(data, list) and len(data) > 0:
                entry = data[0]
                
                # Extract phonetic (IPA notation)
                phonetic = entry.get('phonetic', '')
                if not phonetic and entry.get('phonetics'):
                    # Try to find IPA text in phonetics array
                    for phonetic_item in entry['phonetics']:
                        if 'text' in phonetic_item:
                            phonetic = phonetic_item['text']
                            break
                
                # Extract primary definition and senses
                definitions = []
                part_of_speech = None
                examples = []
                
                # Iterate through meanings (parts of speech)
                for meaning in entry.get('meanings', []):
                    if not part_of_speech:
                        part_of_speech = meaning.get('partOfSpeech', 'noun')
                    
                    # Get definitions for this part of speech
                    for defn in meaning.get('definitions', []):
                        definitions.append(defn.get('definition', ''))
                        if len(examples) < 2:  # collect up to 2 examples
                            example = defn.get('example')
                            if example:
                                examples.append(example)
                    
                    # Get examples from word list if available
                    for ex_obj in meaning.get('example', []):
                        if len(examples) < 2:
                            examples.append(ex_obj)
                
                return {
                    "word": entry.get('word', word),
                    "phonetic": phonetic,
                    "part_of_speech": part_of_speech,
                    "primary_definition": definitions[0] if definitions else None,
                    "other_senses": definitions[1:] if len(definitions) > 1 else [],
                    "examples": examples,
                    "source": "Free Dictionary API"
                }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, Exception):
        pass
    
    return None

def classify_register(word: str, definition: str) -> str:
    """
    Simple heuristic to classify register (formal/informal/neutral).
    In practice, the Free Dictionary API often includes this in definitions.
    """
    lower_def = definition.lower() if definition else ""
    lower_word = word.lower()
    
    formal_markers = ['formal', 'archaic', 'technical', 'academic', 'juridical', 'official']
    informal_markers = ['informal', 'slang', 'colloquial', 'casual', 'vulgar', 'humorous']
    
    if any(m in lower_def for m in formal_markers):
        return "formal"
    elif any(m in lower_def for m in informal_markers):
        return "informal"
    else:
        return "neutral"

def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_definitions.py <word>")
        sys.exit(1)
    
    word = sys.argv[1].strip()
    
    print(f"🔍 Looking up '{word}'...\n")
    
    # Fetch from Free Dictionary API
    result = get_free_dictionary(word)
    
    if result and result['primary_definition']:
        register = classify_register(word, result['primary_definition'])
        
        # Display formatted output
        print(f"✨ Definition of '{result['word']}':\n")
        
        if result.get('phonetic'):
            print(f"Pronunciation (IPA): {result['phonetic']}")
        
        print(f"\nPrimary sense:")
        print(f"  {result['primary_definition']}\n")
        
        if result.get('other_senses'):
            print(f"Other senses:")
            for i, sense in enumerate(result['other_senses'][:2], 1):  # show up to 2
                print(f"  {i}. {sense}")
            print()
        
        if result.get('examples'):
            print(f"Example sentences:")
            for ex in result['examples']:
                print(f"  • {ex}")
            print()
        
        print(f"Part of speech: {result.get('part_of_speech', 'noun')}")
        print(f"Register: {register}")
        print(f"Source: {result['source']}")
        
        # Output clean JSON for programmatic use
        output = {
            "word": result['word'],
            "phonetic": result['phonetic'],
            "primary_definition": result['primary_definition'],
            "other_senses": result['other_senses'],
            "part_of_speech": result.get('part_of_speech', 'noun'),
            "register": register,
            "examples": result.get('examples', []),
            "source": result['source']
        }
        
        print(f"\n--- JSON Output ---")
        print(json.dumps(output, indent=2))
    else:
        print(f"❌ Could not find definition for '{word}'")
        print(f"   The word might be misspelled or too specialized.")
        print(f"\nPlease provide your own definition or check the spelling.")
        sys.exit(1)

if __name__ == '__main__':
    main()
