"""管理员统一操作审计查询（不提供修改或删除接口）。"""
from fastapi import APIRouter, Depends, Query

from ..auth import require_admin
from ..db import q, q1

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("")
def list_audit(actor: str = "", action: str = "", target: str = "", result: str = "",
               correlation_id: str = "", before_id: int | None = None,
               limit: int = Query(100, ge=1, le=500)):
    clauses, args = [], []
    for column, value in (("actor", actor), ("action", action), ("target", target)):
        if value:
            clauses.append(f"instr({column}, ?) > 0")
            args.append(value)
    for field, value in (("result", result), ("correlation_id", correlation_id)):
        if value:
            clauses.append("CASE WHEN json_valid(detail) THEN json_extract(detail, ?) END = ?")
            args.extend((f"$.{field}", value))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = q1("SELECT COUNT(*) AS n FROM audit_log" + where, tuple(args))["n"]
    if before_id is not None:
        clauses.append("id < ?")
        args.append(before_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = q("SELECT id,actor,action,target,detail,at FROM audit_log" + where +
             " ORDER BY id DESC LIMIT ?", (*args, limit + 1))
    items = rows[:limit]
    return {"items": items, "total": total,
            "next_before_id": items[-1]["id"] if len(rows) > limit else None}
