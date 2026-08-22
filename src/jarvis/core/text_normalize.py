"""Pure text functions for the Hinglish/English speech path.

Every function here takes an utterance -- or a response about to be spoken --
and returns a derived value. No state, no `self`, no imports from the rest of
JARVIS. That is what makes this module testable in the minimal environment CI
runs: until this existed, the code below sat inside `main.py`, which imports
PyQt6, ollama and pyautogui at module level, so none of it could be exercised
by a test.

Moved out of `main.py`'s `JARVIS` class verbatim; the bodies are unchanged and
`tests/test_text_normalize.py` checks that they still match, node for node,
what the class held before the move. `main.py` keeps a method of the same name
for each one, delegating here, so every existing call site is untouched.

Not consolidated with their near-namesakes elsewhere, deliberately:

- `jarvis.core.tts_engine.TTSEngine._detect_language` returns `"hi"`/`"en"`,
  needs >2 Devanagari characters, and wants 2 Hindi markers or 15% of the
  words. `detect_language` here returns `"hinglish"`/`"english"` off a single
  marker and any Devanagari at all. Same name, different contract, different
  threshold -- one picks a TTS voice, the other picks a reply language.
- `jarvis.core.audio_engine.AudioEngine._transliterate_devanagari_to_roman`
  is a word-map with a warning for anything unmapped, applied to Whisper's
  output. `transliterate_devanagari_to_roman` here is character-level with a
  word-map in front, applied later in `run()`. Neither is a superset.

Merging either pair would change behaviour on the Hinglish path, which is the
primary interface. They are listed here so the next reader knows the
duplication was measured rather than missed.
"""


def detect_language(text: str) -> str:
    """Detects whether user input is predominantly English or Hinglish/Hindi."""
    has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
    if has_devanagari:
        return "hinglish"
    text_clean = text.lower().strip()
    words = set(text_clean.split())
    hinglish_keywords = {
        "karo", "kardo", "khol", "kholo", "kholna", "kholne", "hai", "hain", "nhi", "nahi",
        "par", "pe", "mein", "me", "ke", "ki", "ka", "ko", "se", "andar", "bahar",
        "saari", "saariya", "sab", "sub", "kuch", "kuchh", "batayein", "batao", "bata",
        "sunao", "chalao", "bajao", "raha", "rahi", "hu", "hoon", "thi", "tha",
        "kya", "kaise", "kyun", "kab", "kahan", "konsa", "so", "jao", "jaao",
        "rehne", "chhod", "hatao", "dekho", "dikhao", "madad", "chahiye", "banana", "karna",
        "khi", "khali", "uske", "baad", "phir", "fir", "unko", "usko", "unse", "isse"
    }
    match_count = len(words.intersection(hinglish_keywords))
    return "hinglish" if match_count >= 1 else "english"


def transliterate_devanagari_to_roman(text: str) -> str:
    """Transliterates Devanagari Hindi text to Roman script Hinglish phonetically."""
    consonants = {
        'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n',
        'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n',
        'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
        'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
        'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm',
        'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
        'ष': 'sh', 'स': 's', 'ह': 'h', 'क्ष': 'ksh', 'त्र': 'tr',
        'ज्ञ': 'gy', 'ड़': 'd', 'ढ़': 'dh'
    }
    vowels = {
        'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
        'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
        'ा': 'a', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
        'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
        'ं': 'n', 'ः': 'h', 'ँ': 'n', '्': ''
    }
    common_words = {
        "एक": "ek", "काम": "kaam", "करो": "karo", "कर": "kar", "दे": "de", "दो": "do",
        "दिखाओ": "dikhao", "दिखा": "dikha", "खोल": "khol", "खोलना": "kholo",
        "बजाओ": "bajao", "बजा": "baja", "चलाओ": "chalao", "चला": "chala",
        "मुझे": "mujhe", "मेरा": "mera", "मेरी": "meri", "तुम": "tum", "तुम्हारा": "tumhara",
        "आप": "aap", "आपका": "aapka", "है": "hai", "हूँ": "hoon", "था": "tha",
        "थी": "thi", "थे": "the", "रहना": "rahna", "रहा": "raha", "रही": "rahi",
        "रहे": "rahe", "करते": "karte", "करती": "karti", "करता": "karta",
        "कहाँ": "kahan", "कब": "kab", "क्यों": "kyun", "कैसे": "kaise", "क्या": "kya",
        "कौन": "kaun", "कुछ": "kuch", "sab": "sab", "और": "aur", "भी": "bhi",
        "तो": "toh", "ye": "yeh", "वह": "woh", "अंडर": "under", "बजेट": "budget",
        "लेप्टोप": "laptop", "लैपटॉप": "laptop", "ब्राउज़र": "browser", "ब्रूवजर": "browser",
        "क्रोम": "chrome", "स्पोटिफ़ाई": "spotify", "स्पॉटीफाई": "spotify",
        "गाने": "gaane", "गाना": "gaana", "बजादो": "bajado", "प्ले": "play",
        "को": "ko", "pe": "pe", "pehle": "pehle", "par": "par", "मम्मी": "mommy", "पापा": "papa"
    }
    words = text.split()
    translated_words = []
    for w in words:
        clean_w = w.strip(",.!?\"'")
        punctuation = w[len(clean_w):] if w.endswith(clean_w) else ""
        lead_punctuation = w[:w.find(clean_w)] if clean_w in w else ""
        if clean_w in common_words:
            translated_words.append(lead_punctuation + common_words[clean_w] + punctuation)
        elif any('\u0900' <= c <= '\u097F' for c in clean_w):
            roman = ""
            i = 0
            while i < len(clean_w):
                char = clean_w[i]
                next_char = clean_w[i+1] if i + 1 < len(clean_w) else ""
                if next_char == '्':
                    if char in consonants:
                        roman += consonants[char]
                    i += 2
                    continue
                if char in consonants:
                    roman += consonants[char]
                    if next_char in vowels and next_char not in ['अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ऋ', 'ए', 'ऐ', 'ओ', 'औ']:
                        roman += vowels[next_char]
                        i += 2
                    else:
                        if next_char not in vowels and next_char != '':
                            roman += 'a'
                        i += 1
                elif char in vowels:
                    roman += vowels[char]
                    i += 1
                else:
                    roman += char
                    i += 1
            translated_words.append(lead_punctuation + roman + punctuation)
        else:
            translated_words.append(w)
    return " ".join(translated_words)


def get_phonetic_candidates(text: str) -> list[str]:
    mappings = {
        "risakhal": "recycle",
        "vine": "bin",
        "tresh": "trash",
        "fayas": "files",
        "dilet": "delete",
        "temathareree": "temporary",
        "kesh": "cache",
        "rimo": "remove",
        "leptob": "laptop",
        "leptop": "laptop",
        "aplication": "application",
        "opun": "open",
        "apen": "open",
        "play music": "play some music",
        "spotifai": "spotify",
        "spotifaee": "spotify",
        "dish clean up": "disk cleanup",
        "dish clean": "disk cleanup",
        "mailware": "malware",
        "garo": "karo",
        "buja": "baja"
    }
    words = text.lower().split()
    modified = False
    candidates = []

    # Word replacement candidate
    replaced_words = []
    for w in words:
        clean_w = w.strip(",.!?\"'")
        punctuation = w[len(clean_w):] if w.endswith(clean_w) else ""
        lead_punctuation = w[:w.find(clean_w)] if clean_w in w else ""
        if clean_w in mappings:
            replaced_words.append(lead_punctuation + mappings[clean_w] + punctuation)
            modified = True
        else:
            replaced_words.append(w)
    if modified:
        candidates.append(" ".join(replaced_words))

    # Substring replacement candidate
    phrase = text.lower()
    phrase_modified = False
    for k, v in mappings.items():
        if k in phrase:
            phrase = phrase.replace(k, v)
            phrase_modified = True
    if phrase_modified:
        candidates.append(phrase)

    return list(set(candidates))


def clean_name_address(text: str) -> str:
    """Strips casual friendly address words ('jarvis', 'jarvis bhai', 'hey jarvis', etc.) from user input."""
    import re
    if not text:
        return text
    pattern = r"\b(hey|sun|sunn|chalo|arre|arrey|oh|bhai)?\s*jarvis\s*(bhai|ji|bro|yaara)?\b"
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(",. ")
    return cleaned if cleaned else text


def split_chained_commands(text: str) -> list[str]:
    import re
    pattern = r"\b(?:and\s+then|then|after\s+that|and\s+after\s+that|uske\s+baad|iske\s+baad|phir|aur\s+phir|aur\s+uske\s+baad)\b"
    splits = re.split(pattern, text, flags=re.IGNORECASE)
    commands = [c.strip() for c in splits if c.strip()]
    return commands


def parse_volume_reply(text: str):
    """Extracts a 0-100 volume level from a Hinglish/English reply. None if not understood."""
    import re
    t = re.sub(r'[,\?\!\.\"\']', '', text.lower()).strip()

    num = re.search(r'(\d{1,3})', t)
    if num:
        return max(0, min(100, int(num.group(1))))

    if any(w in t for w in ["mute", "silent", "band kar", "zero"]):
        return 0
    if any(w in t for w in ["bahut kam", "sabse kam", "very low", "lowest", "ekdum kam"]):
        return 10
    if any(w in t for w in ["kam", "low", "dhime", "dhima", "dheeme", "halka", "halke"]):
        return 25
    if any(w in t for w in ["medium", "normal", "thik", "theek", "aadha", "half", "beech"]):
        return 50
    if any(w in t for w in ["full", "max", "maximum", "poora", "pura", "tez", "loud", "high"]):
        return 100
    return None


def clean_song_name_reply(text: str) -> str:
    """Extracts just the song/video name out of a spoken reply."""
    import re
    t = re.sub(r'[,\?\!\.\"\']', '', text.lower()).strip()

    # User leaves the choice to JARVIS.
    if any(p in t for p in ["koi bhi", "kuch bhi", "jo bhi", "tumhari pasand", "tumhari marzi",
                            "your choice", "anything", "tum decide"]):
        return "trending songs this week"

    t = re.sub(
        r'\b(?:play|chalao|chalado|chala|bajao|bajado|baja|sunao|suna|dikhao|dikha|do|de|karo|'
        r'please|plz|youtube|yt|pe|par|mein|ka|ki|ke|ko|gaana|gana|gaane|song|songs|video|'
        r'naam|hai|wala|wali|sir)\b',
        '', t
    )
    return re.sub(r'\s+', ' ', t).strip()


def clean_to_plain_text(text: str) -> str:
    """Strips markdown formatting, bullet points, numbers, links, and asterisks for conversational speech/viewing."""
    import re
    if not text:
        return ""
    # 1. Remove parenthetical descriptions (e.g. (pauses), (smiling), (breathes softly))
    text = re.sub(r"\([^)]*\)", "", text)

    # 2. Remove markdown images
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # 3. Remove markdown links (keep text, discard URL)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"<(https?://\S+)>", "", text)
    text = re.sub(r"\bhttps?://\S+", "", text)

    # 4. Remove bold/italic asterisks and underscores
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")

    # 5. Remove markdown headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # 6. Clean bullet points at start of lines
    text = re.sub(r"^[ \t]*[-\*+]\s+", "", text, flags=re.MULTILINE)

    # 7. Clean numbered list markers at start of lines or sentences
    text = re.sub(r"^[ \t]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # 8. Join lines into smooth flowing paragraphs
    paragraphs = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            paragraphs.append(line)

    combined = " ".join(paragraphs)
    combined = re.sub(r"\s+", " ", combined).strip()

    # 9. Interactive Turn Truncation:
    # If the text contains an interactive question, truncate the text immediately after the question mark.
    question_match = re.search(r"(\b(?:shall\s+we|would\s+you\s+like|should\s+i|can\s+i|do\s+you\s+want)\b[^?]*\?)", combined, flags=re.IGNORECASE)
    if question_match:
        idx = combined.find(question_match.group(1)) + len(question_match.group(1))
        combined = combined[:idx].strip()

    return combined
