"""Text normalisation shared by the alias table and the extractor.

Both sides of a match must be canonicalised the same way, or the alias
"blood in phlegm" will never match the sentence "no blood in the phlegm".
"""
import re

# Expanded so negation detection can see the word "not". Aliases are written
# in the contracted form, so the alias table is expanded to match.
CONTRACTIONS = [
    ("won't", "will not"),
    ("can't", "can not"),
    ("cannot", "can not"),
    ("n't", " not"),
    ("'ve", " have"),
    ("'m", " am"),
    ("'re", " are"),
    ("'ll", " will"),
    ("'d", " would"),
    ("'s", " is"),
]

# Contracted alias spellings -> their expanded equivalents.
ALIAS_CONTRACTIONS = [
    ("cant", "can not"),
    ("dont", "do not"),
    ("doesnt", "does not"),
    ("didnt", "did not"),
    ("havent", "have not"),
    ("hasnt", "has not"),
    ("wont", "will not"),
    ("isnt", "is not"),
    ("arent", "are not"),
]

# Words that carry no matching signal. Removed from BOTH text and aliases, so
# "my nose is completely blocked" and the alias "nose blocked" line up.
# "no", "not" and "without" are never stripped: negation depends on them.
STOPWORDS = {
    "the", "a", "an", "any", "some",
    "my", "your", "his", "her", "their", "our",
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had",
    "completely", "totally", "absolutely", "quite", "really",
    "just", "still", "also", "even", "actually", "literally",
}

_WORD = re.compile(r"[a-z0-9]+")


def expand_contractions(text: str) -> str:
    out = text
    for pattern, replacement in CONTRACTIONS:
        out = out.replace(pattern, replacement)
    return out


def expand_alias_contractions(alias: str) -> str | None:
    """Expanded spelling of an alias, or None if it has no contraction."""
    out = alias
    for contracted, expanded in ALIAS_CONTRACTIONS:
        out = re.sub(r"\b" + contracted + r"\b", expanded, out)
    return out if out != alias else None


def strip_stopwords(text: str) -> str:
    """Drop stopwords and collapse whitespace."""
    kept = [w for w in text.split() if w not in STOPWORDS]
    return " ".join(kept)


def canonicalise(text: str) -> str:
    """Full canonical form used for alias matching."""
    return strip_stopwords(expand_contractions(text.lower()))


def alias_pattern(alias: str) -> re.Pattern[str]:
    """Regex for a canonical alias.

    Whitespace is flexible and a trailing plural is optional, so "joint pain"
    also matches "joint pains".
    """
    words = _WORD.findall(alias)
    if not words:
        return re.compile(r"(?!x)x")  # never matches
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(r"\b" + body + r"s?\b")
