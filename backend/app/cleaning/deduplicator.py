"""Near-duplicate detection via MinHash (datasketch).

Works at any scale — for TB-scale use datatrove's built-in MinHash dedup.
"""
from __future__ import annotations

from app.domain.document import CleanDocument


def _shingles(text: str, k: int = 5) -> set[str]:
    """Return character k-gram shingles for MinHash."""
    text = text.lower()
    return {text[i: i + k] for i in range(len(text) - k + 1)}


class MinHashDeduplicator:
    """
    Deduplicates ``CleanDocument`` objects using MinHash Jaccard similarity.

    Args:
        num_perm: Number of permutations (higher = more accurate, slower).
        threshold: Jaccard similarity above which two docs are considered duplicates.
    """

    def __init__(self, num_perm: int = 128, threshold: float = 0.85) -> None:
        self._num_perm = num_perm
        self._threshold = threshold
        self._index: object | None = None   # datasketch MinHashLSH

    def _build_index(self) -> object:
        from datasketch import MinHashLSH  # type: ignore[import]
        return MinHashLSH(threshold=self._threshold, num_perm=self._num_perm)

    def _minhash(self, text: str) -> object:
        from datasketch import MinHash  # type: ignore[import]
        m = MinHash(num_perm=self._num_perm)
        for shingle in _shingles(text):
            m.update(shingle.encode("utf-8"))
        return m

    def deduplicate(self, docs: list[CleanDocument]) -> list[CleanDocument]:
        """
        Mark duplicates in-place and return the list with ``is_duplicate`` set.

        The first occurrence of a near-duplicate cluster is kept; subsequent
        ones are marked ``is_duplicate=True``.
        """
        from datasketch import MinHashLSH  # type: ignore[import]

        lsh = MinHashLSH(threshold=self._threshold, num_perm=self._num_perm)
        results: list[CleanDocument] = []

        for doc in docs:
            if len(doc.text) < 50:
                results.append(doc)
                continue

            m = self._minhash(doc.text)
            key = str(doc.id)

            # Store signature for future comparisons
            doc.minhash_signature = list(m.hashvalues)

            try:
                neighbors = lsh.query(m)
            except Exception:
                neighbors = []

            if neighbors:
                doc = doc.model_copy(update={"is_duplicate": True})
            else:
                lsh.insert(key, m)

            results.append(doc)

        return results

    def is_duplicate(self, text: str, existing_signatures: list[list[int]]) -> bool:
        """Check a single text against a list of existing MinHash signatures."""
        from datasketch import MinHash  # type: ignore[import]

        m = self._minhash(text)
        for sig in existing_signatures:
            existing = MinHash(num_perm=self._num_perm, hashvalues=sig)
            if m.jaccard(existing) >= self._threshold:
                return True
        return False
