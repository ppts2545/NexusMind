"""Dataset builder — quality filter + deduplication + sample creation."""
from __future__ import annotations

from app.core.config import get_settings
from app.domain.dataset import DatasetSample


class DatasetBuilder:
    """
    Processes raw text into clean dataset samples.

    Designed to be called either directly (small-scale) or via a datatrove
    pipeline for TB-scale processing.

    datatrove drop-in (future)::

        from datatrove.pipeline.readers import WarcReader
        from datatrove.pipeline.filters import LanguageFilter, GopherQualityFilter
        from datatrove.pipeline.dedup import MinhashDedupFilter
        from datatrove.pipeline.writers import JsonlWriter

        pipeline = [
            WarcReader(data_folder="s3://commoncrawl/..."),
            LanguageFilter(languages=["en"]),
            GopherQualityFilter(),
            MinhashDedupFilter(),
            JsonlWriter(output_folder="s3://my-datasets/"),
        ]
    """

    def __init__(
        self,
        min_words: int = 50,
        max_words: int = 100_000,
        languages: list[str] | None = None,
        deduplicate: bool = True,
        source_types: list[str] | None = None,
    ) -> None:
        settings = get_settings()
        self._min_words = min_words
        self._max_words = max_words
        self._languages = set(languages or ["en"])
        self._deduplicate = deduplicate
        self._source_types = set(source_types) if source_types else None

        self._minhash_num_perm = settings.MINHASH_NUM_PERM
        self._minhash_threshold = settings.MINHASH_THRESHOLD

    def process_text(self, text: str, source: str = "", language: str = "en") -> DatasetSample | None:
        """Convert raw text into a DatasetSample, or return None if it fails filters."""
        words = text.split()
        word_count = len(words)

        if word_count < self._min_words or word_count > self._max_words:
            return None

        if self._languages and language not in self._languages:
            return None

        return DatasetSample(
            text=text,
            source=source,
            language=language,
            word_count=word_count,
        )

    def deduplicate(self, samples: list[DatasetSample]) -> list[DatasetSample]:
        """Remove near-duplicates using MinHash."""
        if not self._deduplicate or not samples:
            return samples

        try:
            from datasketch import MinHash, MinHashLSH  # type: ignore[import]
        except ImportError:
            return samples

        lsh = MinHashLSH(threshold=self._minhash_threshold, num_perm=self._minhash_num_perm)
        unique: list[DatasetSample] = []

        for sample in samples:
            m = MinHash(num_perm=self._minhash_num_perm)
            for token in set(sample.text.lower().split()):
                m.update(token.encode("utf-8"))

            key = str(sample.id)
            try:
                neighbors = lsh.query(m)
            except Exception:
                neighbors = []

            if not neighbors:
                lsh.insert(key, m)
                unique.append(sample)

        return unique

    def build_instruction_samples(
        self,
        text: str,
        source: str = "",
    ) -> list[dict]:
        """
        Generate simple QA instruction pairs from a text passage.

        For production fine-tuning, replace this with an LLM-assisted
        instruction generation pipeline.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.split()) > 20]
        samples: list[dict] = []

        for para in paragraphs[:10]:
            samples.append(
                {
                    "instruction": "Summarize the following passage.",
                    "input": para[:500],
                    "output": para[:200] + ("..." if len(para) > 200 else ""),
                    "source": source,
                }
            )

        return samples
