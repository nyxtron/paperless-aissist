"""Processing statistics and SSE log streaming endpoints."""

import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlmodel import select, func
from datetime import datetime, timedelta, timezone

from ..database import get_async_session
from ..models import ProcessingLog
from ..schemas import DailyStatsItem, RecentLogItem, StatsResponse
from ..services.log_stream import get_history, subscribe, unsubscribe

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.delete("/reset")
async def reset_stats():
    try:
        async with get_async_session() as session:
            from sqlalchemy import delete

            stmt = delete(ProcessingLog)
            await session.exec(stmt)
        return {"success": True, "message": "All processing logs have been deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("", response_model=StatsResponse)
async def get_stats():
    async with get_async_session() as session:
        total_stmt = select(func.count(ProcessingLog.id))
        total = await session.exec(total_stmt)
        total = total.one()

        success_stmt = select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "success"
        )
        success = await session.exec(success_stmt)
        success = success.one()

        failed_stmt = select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "failed"
        )
        failed = await session.exec(failed_stmt)
        failed = failed.one()

        skipped_stmt = select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "skipped"
        )
        skipped = await session.exec(skipped_stmt)
        skipped = skipped.one()

        avg_time_stmt = select(func.avg(ProcessingLog.processing_time_ms))
        avg_time = await session.exec(avg_time_stmt)
        avg_time = avg_time.one()

        return StatsResponse(
            total_processed=total,
            success_rate=round((success / total * 100) if total > 0 else 0, 2),
        )


@router.get("/daily", response_model=list[DailyStatsItem])
async def get_daily_stats(days: int = 7):
    days = min(max(days, 1), 365)
    async with get_async_session() as session:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        daily_stats = {}
        for i in range(days):
            day = (datetime.now(timezone.utc) - timedelta(days=i)).date()
            daily_stats[day.isoformat()] = {"success": 0, "failed": 0, "skipped": 0}

        stmt = select(ProcessingLog).where(ProcessingLog.processed_at >= start_date)
        logs = await session.exec(stmt)
        logs = logs.all()

        for log in logs:
            day = log.processed_at.date().isoformat()
            if day in daily_stats:
                if log.status in daily_stats[day]:
                    daily_stats[day][log.status] += 1

        return [
            DailyStatsItem(
                date=date,
                total=stats["success"] + stats["failed"] + stats["skipped"],
                success=stats["success"],
                failed=stats["failed"],
            )
            for date, stats in sorted(daily_stats.items())
        ]


@router.get("/recent", response_model=list[RecentLogItem])
async def get_recent_logs(limit: int = 20):
    limit = min(max(limit, 1), 1000)
    async with get_async_session() as session:
        stmt = (
            select(ProcessingLog)
            .order_by(ProcessingLog.processed_at.desc())
            .limit(limit)
        )
        logs = await session.exec(stmt)
        logs = logs.all()

        return [
            RecentLogItem(
                id=log.id,
                document_id=log.document_id,
                document_title=log.document_title,
                status=log.status,
                provider=log.llm_provider,
                model=log.llm_model,
                error_message=log.error_message,
                processing_time_ms=log.processing_time_ms,
                created_at=log.processed_at.isoformat() if log.processed_at else None,
            )
            for log in logs
        ]


@router.get("/logs")
async def get_logs():
    return {"lines": get_history()}


@router.get("/logs/stream")
async def stream_logs():
    async def event_gen():
        for line in get_history():
            yield f"data: {json.dumps(line)}\n\n"
        q = await subscribe()
        try:
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(line)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/document/{doc_id}")
async def get_log_by_document(doc_id: int):
    async with get_async_session() as session:
        stmt = (
            select(ProcessingLog)
            .where(ProcessingLog.document_id == doc_id)
            .order_by(ProcessingLog.processed_at.desc())
            .limit(1)
        )
        log = await session.exec(stmt)
        log = log.first()

        if not log:
            return {"error": "No processing log found for this document"}

        return {
            "id": log.id,
            "document_id": log.document_id,
            "document_title": log.document_title,
            "status": log.status,
            "llm_provider": log.llm_provider,
            "llm_model": log.llm_model,
            "llm_response": log.llm_response,
            "error_message": log.error_message,
            "processing_time_ms": log.processing_time_ms,
            "processed_at": log.processed_at.isoformat(),
        }
