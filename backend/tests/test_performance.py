"""Performance regressions, asserted structurally rather than by stopwatch.

Timing assertions in a test suite are flaky on shared hardware and get muted
the first time CI is busy. These check the MECHANISM instead -- that the cache
is consulted, that the pre-filter narrows the search -- which is what would
actually be removed by a careless edit.

The two things being protected, both found by profiling rather than guesswork:

  * `embed_query` was 35.9 ms of a 41.6 ms retrieval step, and retrieval was
    88% of all non-LLM time. Memoising it took the step to 0.036 ms.
  * `_match_clause` tested all 789 aliases against every clause -- ~3,900
    regex scans per message. Bucketing by first word took extraction from
    4.45 ms to 1.03 ms.
"""
from core import knowledge
from core.symptom_extraction import _aliases_by_first_word, _candidate_aliases, extract
from rag import embedder


def test_the_query_embedding_is_memoised():
    """Without this the transformer runs on every consultation."""
    embedder.reset_cache()
    query = "Dengue Fever: symptoms, warning signs, self care"

    first = embedder.embed_query(query)
    info_after_first = embedder._embed_query_cached.cache_info()
    second = embedder.embed_query(query)
    info_after_second = embedder._embed_query_cached.cache_info()

    assert info_after_second.hits == info_after_first.hits + 1, (
        "the second identical query re-ran the model instead of hitting the cache"
    )
    assert first is second, "cache returned a copy rather than the stored vector"


def test_a_cached_embedding_cannot_be_mutated_in_place():
    """A caller writing to the returned array would corrupt every later hit."""
    embedder.reset_cache()
    vector = embedder.embed_query("Influenza (Flu): symptoms")
    assert not vector.flags.writeable


def test_the_alias_prefilter_actually_narrows_the_search():
    total = len(knowledge.alias_index())
    candidates = _candidate_aliases("fever and cough")

    assert len(candidates) < total / 5, (
        f"pre-filter returned {len(candidates)} of {total} aliases; it is not "
        "narrowing anything and extraction is back to scanning the whole table"
    )
    assert candidates, "pre-filter returned nothing for an obvious clause"


def test_the_prefilter_preserves_longest_first_ordering():
    """The matcher depends on it: "dry cough" must be tried before "cough"."""
    candidates = _candidate_aliases("dry cough and sore throat")
    lengths = [len(alias) for alias, _code in candidates]
    assert lengths == sorted(lengths, reverse=True), "ordering was lost"


def test_the_prefilter_still_finds_plural_forms():
    """`alias_pattern` allows a trailing plural, so bucketing on the exact
    first word alone would drop "loose motions" against the alias "loose
    motion"."""
    codes = {s.code for s in extract("loose motions since yesterday")}
    assert "diarrhoea" in codes


def test_every_alias_is_reachable_through_some_bucket():
    """A pre-filter that silently drops aliases would lose symptoms with no
    error anywhere -- the extractor would just stop seeing them."""
    buckets = _aliases_by_first_word()
    bucketed = sum(len(v) for v in buckets.values())
    assert bucketed == len(knowledge.alias_index())
