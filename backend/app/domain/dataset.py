from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DatasetFormat(str, Enum):
    JSONL = "jsonl"
    PARQUET = "parquet"
    HUGGINGFACE = "huggingface"


class DatasetType(str, Enum):
    PRETRAINING = "pretraining"        # raw text, no instruction/response
    FINETUNING = "finetuning"          # instruction + response pairs
    INSTRUCTION = "instruction"        # alpaca-style instruction tuning


class DatasetConfig(BaseModel):
    """Parameters for a dataset build job."""

    name: str
    dataset_type: DatasetType = DatasetType.PRETRAINING
    output_format: DatasetFormat = DatasetFormat.JSONL
    # Filtering
    min_words: int = 50
    max_words: int = 100_000
    languages: list[str] = Field(default_factory=lambda: ["en"])
    deduplicate: bool = True
    # Source filtering (None = all)
    source_types: list[str] | None = None
    # Optional output path override
    output_path: str | None = None


class DatasetSample(BaseModel):
    """A single row in a pre-training or fine-tuning dataset."""

    id: UUID = Field(default_factory=uuid4)
    text: str                            # pre-training: raw text; fine-tuning: full conversation
    source: str
    language: str = "en"
    word_count: int = 0
    metadata: dict = Field(default_factory=dict)


class InstructionSample(BaseModel):
    """Alpaca-style instruction tuning sample."""

    id: UUID = Field(default_factory=uuid4)
    instruction: str
    input: str = ""
    output: str
    source: str
    metadata: dict = Field(default_factory=dict)


class DatasetBuildResult(BaseModel):
    job_id: UUID
    name: str
    output_path: str
    output_format: DatasetFormat
    total_samples: int
    deduplicated_count: int
    filtered_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
