"""
Embedding fine-tuner using MultipleNegativesRankingLoss.

How it works:
  1. Pull QueryLogs where feedback_score >= POSITIVE_THRESHOLD
  2. Each log yields (query_text, chunk_content) positive pairs
  3. Train with MNR loss — in-batch negatives (all other chunks in the batch)
  4. Save fine-tuned model to disk
  5. Caller is responsible for reloading the Embedder and re-indexing ChromaDB

Why MNR loss?
  - No explicit negative labels needed — other batch items serve as negatives
  - Sample-efficient: good results with as few as 50 pairs
  - Standard approach for domain-adaptive retrieval fine-tuning
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class TrainingPair:
    query: str
    chunk: str
    is_positive: bool


@dataclass
class FinetuneResult:
    output_path: str
    training_samples: int
    epochs: int
    final_loss: float


def build_training_pairs(query_logs: list[dict]) -> list[TrainingPair]:
    """
    Convert QueryLog rows into (query, chunk) pairs.

    A log row looks like:
      {
        query_text: str,
        feedback_score: int,                 # 1–5
        retrieved_chunks: [{content, score}]
      }
    """
    pairs: list[TrainingPair] = []
    for log in query_logs:
        score = log.get("feedback_score")
        chunks = log.get("retrieved_chunks") or []
        query = log["query_text"].strip()

        if not query or not chunks:
            continue

        if score is not None and score >= settings.FINETUNE_POSITIVE_THRESHOLD:
            for c in chunks:
                content = c.get("content", "").strip()
                if content:
                    pairs.append(TrainingPair(query=query, chunk=content, is_positive=True))

        elif score is not None and score <= settings.FINETUNE_NEGATIVE_THRESHOLD:
            # Store hard negatives — used as explicit negative InputExamples
            # with label=0 if switching to CosineSimilarityLoss in the future.
            # For MNR loss we skip these; they act as in-batch negatives naturally.
            pass

    return pairs


def run_finetune(base_model_path: str, query_logs: list[dict]) -> FinetuneResult:
    """
    Synchronous fine-tuning — run inside a Celery worker process.
    Returns the path to the saved model.
    """
    pairs = build_training_pairs(query_logs)
    n_positive = len(pairs)

    if n_positive < settings.FINETUNE_MIN_SAMPLES:
        raise ValueError(
            f"Not enough training data: {n_positive} positive pairs "
            f"(need >= {settings.FINETUNE_MIN_SAMPLES}). "
            "Collect more user feedback first."
        )

    logger.info("finetune_start", base_model=base_model_path, samples=n_positive)

    model = SentenceTransformer(base_model_path)

    examples = [InputExample(texts=[p.query, p.chunk]) for p in pairs]
    loader = DataLoader(examples, shuffle=True, batch_size=settings.FINETUNE_BATCH_SIZE)
    loss_fn = losses.MultipleNegativesRankingLoss(model)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(settings.FINE_TUNED_MODEL_DIR, f"bge_nexusmind_{timestamp}")
    os.makedirs(output_path, exist_ok=True)

    model.fit(
        train_objectives=[(loader, loss_fn)],
        epochs=settings.FINETUNE_EPOCHS,
        warmup_steps=settings.FINETUNE_WARMUP_STEPS,
        output_path=output_path,
        show_progress_bar=False,
    )

    # Capture final loss from the last evaluator step (approximate)
    final_loss = float("nan")
    try:
        import glob, json
        log_files = sorted(glob.glob(os.path.join(output_path, "*.json")))
        if log_files:
            with open(log_files[-1]) as f:
                data = json.load(f)
                final_loss = list(data.values())[-1] if data else float("nan")
    except Exception:
        pass

    logger.info("finetune_complete", output_path=output_path, samples=n_positive)
    return FinetuneResult(
        output_path=output_path,
        training_samples=n_positive,
        epochs=settings.FINETUNE_EPOCHS,
        final_loss=final_loss,
    )
