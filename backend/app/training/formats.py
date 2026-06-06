"""Dataset format writers — JSONL, Parquet, HuggingFace Dataset."""
from __future__ import annotations

import json
from pathlib import Path

from app.domain.dataset import DatasetFormat, DatasetSample


def write_dataset(
    samples: list[DatasetSample],
    output_path: str,
    fmt: DatasetFormat,
) -> tuple[int, int, int]:
    """
    Write samples to disk in the requested format.

    Returns (total_written, deduped_count, filtered_count).
    """
    total = len(samples)
    deduped = 0
    filtered = 0

    if fmt == DatasetFormat.JSONL:
        written = _write_jsonl(samples, output_path)
    elif fmt == DatasetFormat.PARQUET:
        written = _write_parquet(samples, output_path)
    elif fmt == DatasetFormat.HUGGINGFACE:
        written = _write_huggingface(samples, output_path)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    return written, deduped, filtered


def _write_jsonl(samples: list[DatasetSample], path: str) -> int:
    written = 0
    with open(path, "w", encoding="utf-8") as f:
        for sample in samples:
            row = {
                "text": sample.text,
                "source": sample.source,
                "language": sample.language,
                "word_count": sample.word_count,
                "metadata": sample.metadata,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    return written


def _write_parquet(samples: list[DatasetSample], path: str) -> int:
    try:
        import pyarrow as pa  # type: ignore[import]
        import pyarrow.parquet as pq  # type: ignore[import]
    except ImportError as e:
        raise RuntimeError("pyarrow is required for Parquet output. pip install pyarrow") from e

    rows = {
        "text": [s.text for s in samples],
        "source": [s.source for s in samples],
        "language": [s.language for s in samples],
        "word_count": [s.word_count for s in samples],
    }

    table = pa.table(rows)
    pq.write_table(table, path, compression="snappy")
    return len(samples)


def _write_huggingface(samples: list[DatasetSample], path: str) -> int:
    try:
        from datasets import Dataset  # type: ignore[import]
    except ImportError as e:
        raise RuntimeError("datasets is required for HuggingFace output. pip install datasets") from e

    rows = [
        {
            "text": s.text,
            "source": s.source,
            "language": s.language,
            "word_count": s.word_count,
        }
        for s in samples
    ]

    ds = Dataset.from_list(rows)
    # Save as Arrow dataset directory
    ds.save_to_disk(path)
    return len(samples)
