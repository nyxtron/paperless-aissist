from fastapi import APIRouter
from sqlmodel import select, func
from datetime import datetime, timedelta

from ..database import get_session
from ..models import ProcessingLog

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.delete("/reset")
async def reset_stats():
    try:
        with get_session() as session:
            session.query(ProcessingLog).delete()
        return {"success": True, "message": "All processing logs have been deleted"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("")
async def get_stats():
    with get_session() as session:
        total_stmt = select(func.count(ProcessingLog.id))
        total = session.exec(total_stmt).one()
        
        success_stmt = select(func.count(ProcessingLog.id)).where(ProcessingLog.status == "success")
        success = session.exec(success_stmt).one()
        
        failed_stmt = select(func.count(ProcessingLog.id)).where(ProcessingLog.status == "failed")
        failed = session.exec(failed_stmt).one()
        
        skipped_stmt = select(func.count(ProcessingLog.id)).where(ProcessingLog.status == "skipped")
        skipped = session.exec(skipped_stmt).one()
        
        avg_time_stmt = select(func.avg(ProcessingLog.processing_time_ms))
        avg_time = session.exec(avg_time_stmt).one()
        
        return {
            "total_processed": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "success_rate": round((success / total * 100) if total > 0 else 0, 2),
            "avg_processing_time_ms": round(avg_time, 2) if avg_time else 0,
        }


@router.get("/daily")
async def get_daily_stats(days: int = 7):
    with get_session() as session:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        daily_stats = {}
        for i in range(days):
            day = (datetime.utcnow() - timedelta(days=i)).date()
            daily_stats[day.isoformat()] = {"success": 0, "failed": 0, "skipped": 0}
        
        stmt = select(ProcessingLog).where(ProcessingLog.processed_at >= start_date)
        logs = session.exec(stmt).all()
        
        for log in logs:
            day = log.processed_at.date().isoformat()
            if day in daily_stats:
                if log.status in daily_stats[day]:
                    daily_stats[day][log.status] += 1
        
        return [
            {"date": date, "success": stats["success"], "failed": stats["failed"], "skipped": stats["skipped"]}
            for date, stats in sorted(daily_stats.items())
        ]


@router.get("/recent")
async def get_recent_logs(limit: int = 20):
    with get_session() as session:
        stmt = select(ProcessingLog).order_by(ProcessingLog.processed_at.desc()).limit(limit)
        logs = session.exec(stmt).all()
        
        return [
            {
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
            for log in logs
        ]


@router.get("/document/{doc_id}")
async def get_log_by_document(doc_id: int):
    with get_session() as session:
        stmt = select(ProcessingLog).where(ProcessingLog.document_id == doc_id).order_by(ProcessingLog.processed_at.desc()).limit(1)
        log = session.exec(stmt).first()
        
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
