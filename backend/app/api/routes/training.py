import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import QueryLog, TrainingRun, TrainingRunStatus
from app.db.session import get_db
from app.workers.tasks import fine_tune_embedder

router = APIRouter(prefix="/training", tags=["training"])
settings = get_settings()


class TrainingRunResponse(BaseModel):
    id: uuid.UUID
    status: str
    base_model: str
    output_model_path: str | None
    training_samples: int
    epochs: int
    train_loss: float | None
    reindex_completed: bool
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DatasetStats(BaseModel):
    total_logs: int
    labelled_logs: int
    positive_pairs: int
    negative_pairs: int
    unlabelled_logs: int
    ready_to_train: bool
    reason: str | None


@router.get("/dataset", response_model=DatasetStats)
async def dataset_stats(db: AsyncSession = Depends(get_db)):
    """Show how much feedback data is available and whether training is feasible."""
    total = (await db.execute(select(func.count()).select_from(QueryLog))).scalar_one()
    labelled = (
        await db.execute(
            select(func.count()).select_from(QueryLog).where(QueryLog.feedback_score.isnot(None))
        )
    ).scalar_one()
    positive = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.feedback_score >= settings.FINETUNE_POSITIVE_THRESHOLD)
            .where(QueryLog.retrieved_chunks.isnot(None))
        )
    ).scalar_one()
    negative = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.feedback_score <= settings.FINETUNE_NEGATIVE_THRESHOLD)
            .where(QueryLog.retrieved_chunks.isnot(None))
        )
    ).scalar_one()

    # each positive log can yield multiple pairs (one per retrieved chunk, typically 3–5)
    estimated_pairs = positive * 3
    ready = estimated_pairs >= settings.FINETUNE_MIN_SAMPLES
    reason = (
        None
        if ready
        else f"Need ~{settings.FINETUNE_MIN_SAMPLES} positive pairs; "
        f"estimated {estimated_pairs} from {positive} high-rated logs. "
        f"Collect more 4–5 star feedback."
    )

    return DatasetStats(
        total_logs=total,
        labelled_logs=labelled,
        positive_pairs=estimated_pairs,
        negative_pairs=negative,
        unlabelled_logs=total - labelled,
        ready_to_train=ready,
        reason=reason,
    )


@router.post("/run", response_model=TrainingRunResponse, status_code=202)
async def trigger_training(db: AsyncSession = Depends(get_db)):
    """Kick off an async fine-tuning job. Returns immediately with the run record."""
    # block if a run is already in progress
    in_progress = (
        await db.execute(
            select(TrainingRun).where(TrainingRun.status == TrainingRunStatus.RUNNING).limit(1)
        )
    ).scalar_one_or_none()
    if in_progress:
        raise HTTPException(
            status_code=409,
            detail=f"Training already in progress (run {in_progress.id}). Wait for it to finish.",
        )

    run = TrainingRun(
        id=uuid.uuid4(),
        base_model=settings.FINE_TUNED_MODEL_DIR
        if _fine_tuned_exists()
        else settings.EMBEDDING_MODEL,
        status=TrainingRunStatus.RUNNING,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    fine_tune_embedder.delay(str(run.id))
    return run


@router.get("/runs", response_model=list[TrainingRunResponse])
async def list_runs(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TrainingRun).order_by(TrainingRun.started_at.desc()).limit(limit)
    )
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return run


def _fine_tuned_exists() -> bool:
    import os
    d = settings.FINE_TUNED_MODEL_DIR
    return os.path.isdir(d) and bool(os.listdir(d))
