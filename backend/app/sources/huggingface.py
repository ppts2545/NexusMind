"""HuggingFace Datasets source."""
from __future__ import annotations

from app.domain.document import Document, SourceType
from app.sources.base import BaseSource


class HuggingFaceSource(BaseSource):
    """
    Load documents from a HuggingFace dataset.

    Supports any dataset with a text column (configurable).
    Useful for seeding the knowledge base with public corpora.

    Example::

        src = HuggingFaceSource(
            dataset_name="wikipedia",
            subset="20231101.en",
            split="train",
            text_column="text",
            title_column="title",
            max_samples=10_000,
        )
        docs = await src.load()
    """

    def __init__(
        self,
        dataset_name: str,
        subset: str | None = None,
        split: str = "train",
        text_column: str = "text",
        title_column: str | None = None,
        url_column: str | None = None,
        max_samples: int | None = None,
        hf_token: str | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self._dataset_name = dataset_name
        self._subset = subset
        self._split = split
        self._text_col = text_column
        self._title_col = title_column
        self._url_col = url_column
        self._max_samples = max_samples
        self._hf_token = hf_token
        self._cache_dir = cache_dir

    async def load(self) -> list[Document]:
        import asyncio
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> list[Document]:
        from datasets import load_dataset  # type: ignore[import]

        kwargs: dict = dict(
            split=self._split,
            token=self._hf_token or None,
        )
        if self._cache_dir:
            kwargs["cache_dir"] = self._cache_dir
        if self._subset:
            dataset = load_dataset(self._dataset_name, self._subset, **kwargs)
        else:
            dataset = load_dataset(self._dataset_name, **kwargs)

        if self._max_samples:
            dataset = dataset.select(range(min(self._max_samples, len(dataset))))

        documents: list[Document] = []
        source_label = f"huggingface:{self._dataset_name}"
        if self._subset:
            source_label += f"/{self._subset}"

        for row in dataset:
            text = row.get(self._text_col, "") or ""
            if not text.strip():
                continue

            title = ""
            if self._title_col:
                title = str(row.get(self._title_col, "") or "")
            if not title:
                title = text[:80].replace("\n", " ").strip()

            url = None
            if self._url_col:
                url = row.get(self._url_col)

            metadata = {k: v for k, v in row.items() if k not in (self._text_col, self._title_col, self._url_col)}

            documents.append(
                Document(
                    source=source_label,
                    source_type=SourceType.HUGGINGFACE,
                    url=url,
                    title=title,
                    text=text,
                    metadata=metadata,
                )
            )

        return documents

    async def stream(self):
        import asyncio
        from datasets import load_dataset  # type: ignore[import]

        def _iter():
            kwargs: dict = dict(split=self._split, streaming=True)
            if self._hf_token:
                kwargs["token"] = self._hf_token
            if self._subset:
                dataset = load_dataset(self._dataset_name, self._subset, **kwargs)
            else:
                dataset = load_dataset(self._dataset_name, **kwargs)
            count = 0
            for row in dataset:
                if self._max_samples and count >= self._max_samples:
                    break
                yield row
                count += 1

        source_label = f"huggingface:{self._dataset_name}"
        for row in await asyncio.to_thread(lambda: list(_iter())):
            text = row.get(self._text_col, "") or ""
            if not text.strip():
                continue
            title = str(row.get(self._title_col or "", "") or text[:80])
            yield Document(
                source=source_label,
                source_type=SourceType.HUGGINGFACE,
                title=title,
                text=text,
                metadata={},
            )
