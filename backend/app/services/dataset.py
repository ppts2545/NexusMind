"""Dataset service — scans storage, filters, deduplicates, exports."""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.dataset import DatasetBuildResult, DatasetConfig
from app.storage.base import ObjectStorage

logger = get_logger(__name__)


class DatasetService:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage
        self._settings = get_settings()

    async def build(self, config: DatasetConfig, job_id: str | None = None) -> DatasetBuildResult:
        from app.training.dataset_builder import DatasetBuilder
        from app.training.formats import write_dataset

        builder = DatasetBuilder(
            min_words=config.min_words,
            max_words=config.max_words,
            languages=config.languages,
            deduplicate=config.deduplicate,
            source_types=config.source_types,
        )

        # Stream clean documents from object storage
        keys = await self._storage.list_prefix("clean/")
        logger.info("dataset_scan", total_keys=len(keys), job_id=job_id)

        samples = []
        for key in keys:
            try:
                text = await self._storage.get_text(key)
                sample = builder.process_text(text, source=key)
                if sample:
                    samples.append(sample)
            except Exception as exc:
                logger.warning("dataset_skip", key=key, error=str(exc))

        samples = builder.deduplicate(samples)

        output_path = config.output_path or str(
            Path(self._settings.DATASET_OUTPUT_DIR) / f"{config.name}.{config.output_format}"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        total, deduped, filtered = write_dataset(samples, output_path, config.output_format)

        # Upload to object storage
        if Path(output_path).exists():
            data = Path(output_path).read_bytes()
            storage_key = f"datasets/{config.name}.{config.output_format}"
            await self._storage.put(storage_key, data)

        result = DatasetBuildResult(
            job_id=uuid.UUID(job_id) if job_id else uuid.uuid4(),
            name=config.name,
            output_path=output_path,
            output_format=config.output_format,
            total_samples=total,
            deduplicated_count=deduped,
            filtered_count=filtered,
        )

        logger.info(
            "dataset_built",
            name=config.name,
            samples=total,
            deduped=deduped,
            filtered=filtered,
        )

        return result
