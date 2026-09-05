"""秘密库 API（admin 专属；FR-INIT-013/014/015/016 一期形态）

元数据透明：列表/详情永不含秘密值；值只在显式 reveal/download/export 时解密，全部写审计。
"""
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth import require_admin
from ..db import audit, q
from ..vault import crypto, exporter, store

router = APIRouter(prefix="/api/vault", tags=["vault"], dependencies=[Depends(require_admin)])

_MAX_SIZE = 10 * 1024 * 1024  # 单条秘密/文件上限 10MB


class TextBody(BaseModel):
    name: str
    value: str
    scope: str = "infra"
    secret_type: str = "password"
    rotation_risk: str = "coordinated"
    summary: str = ""
    owner: str = ""
    expires_at: float | None = None


class MetaBody(BaseModel):
    summary: str | None = None
    owner: str | None = None
    expires_at: float | None = None
    secret_type: str | None = None
    rotation_risk: str | None = None


class ValueBody(BaseModel):
    value: str


def _target(row: dict) -> str:
    return f"{row['scope']}/{row['name']}"


def _get_or_404(sid: int) -> dict:
    row = store.get_row(sid)
    if not row:
        raise HTTPException(status_code=404, detail="秘密不存在")
    return row


@router.get("")
def list_secrets(scope: str = ""):
    """元数据清单（透明资源视图，永不含值）。"""
    return store.list_meta(scope)


@router.get("/export")
def export_all(user: dict = Depends(require_admin)):
    """全量导出：明文 manifest + age 密文负载（ADR-0041）。"""
    blob, count = exporter.build_export()
    audit(user["username"], "vault.export", "", f"count={count}")
    filename = time.strftime("vault-export-%Y%m%dT%H%M%S.tar")
    return Response(content=blob, media_type="application/x-tar",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/audit")
def vault_audit():
    return q("SELECT id, actor, action, target, detail, at FROM audit_log"
             " WHERE action LIKE 'vault.%' ORDER BY id DESC LIMIT 500")


@router.get("/master")
def master_info():
    path = crypto.master_key_path()
    return {"recipient": crypto.recipient_str(), "path": str(path), "exists": path.exists()}


@router.post("/master/reveal")
def master_reveal(user: dict = Depends(require_admin)):
    """显示主密钥（admin 专属，写审计；主密钥本就在宿主文件上，此接口只省一步手工开文件）。"""
    identity, _ = crypto.ensure_identity()
    audit(user["username"], "vault.master_reveal")
    return {"secret": str(identity)}


@router.post("/text")
def create_text(body: TextBody, user: dict = Depends(require_admin)):
    try:
        sid = store.create(kind="text", name=body.name, scope=body.scope,
                           plain=body.value.encode("utf-8"), actor=user["username"],
                           secret_type=body.secret_type, rotation_risk=body.rotation_risk,
                           summary=body.summary, owner=body.owner, expires_at=body.expires_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.create", f"{body.scope}/{body.name}", "kind=text")
    return {"id": sid}


@router.post("/file")
async def create_file(user: dict = Depends(require_admin),
                      file: UploadFile = File(...),
                      name: str = Form(""), scope: str = Form("infra"),
                      secret_type: str = Form("access-key"), rotation_risk: str = Form("critical"),
                      summary: str = Form(""), owner: str = Form(""),
                      expires_at: float | None = Form(None)):
    data = await file.read()
    if len(data) > _MAX_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 10MB 上限")
    final_name = name or (file.filename or "").rsplit(".", 1)[0]
    try:
        sid = store.create(kind="file", name=final_name, scope=scope, plain=data,
                           actor=user["username"], secret_type=secret_type,
                           rotation_risk=rotation_risk, summary=summary, owner=owner,
                           expires_at=expires_at, filename=file.filename or final_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.create", f"{scope}/{final_name}", f"kind=file size={len(data)}")
    return {"id": sid}


@router.get("/{sid:int}")
def get_meta(sid: int):
    return store.get_meta(sid) or (_ for _ in ()).throw(HTTPException(404, "秘密不存在"))


@router.post("/{sid:int}/reveal")
def reveal(sid: int, user: dict = Depends(require_admin)):
    """显示文本秘密的值（写审计，响应 no-store）。"""
    row = _get_or_404(sid)
    if row["kind"] != "text":
        raise HTTPException(status_code=400, detail="文件型秘密请用下载")
    audit(user["username"], "vault.reveal", _target(row))
    return Response(content=store.decrypt_value(row), media_type="text/plain; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@router.get("/{sid:int}/download")
def download(sid: int, user: dict = Depends(require_admin)):
    row = _get_or_404(sid)
    audit(user["username"], "vault.download", _target(row),
          row["filename"] if row["kind"] == "file" else "")
    filename = row["filename"] or f"{row['name']}.txt"
    return Response(content=store.decrypt_value(row), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.patch("/{sid:int}")
def update_meta(sid: int, body: MetaBody, user: dict = Depends(require_admin)):
    row = _get_or_404(sid)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        store.update_meta(sid, fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.update", _target(row), ",".join(sorted(fields)))
    return {"ok": True}


@router.post("/{sid:int}/value")
def rotate_value(sid: int, body: ValueBody, user: dict = Depends(require_admin)):
    """轮换文本秘密的值（旧值不可恢复）。"""
    row = _get_or_404(sid)
    if row["kind"] != "text":
        raise HTTPException(status_code=400, detail="文件型秘密请删除后重新上传")
    try:
        store.replace_value(sid, body.value.encode("utf-8"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.rotate", _target(row), f"rotation_risk={row['rotation_risk']}")
    return {"ok": True}


@router.delete("/{sid:int}")
def delete_secret(sid: int, user: dict = Depends(require_admin)):
    row = store.delete(sid)
    if not row:
        raise HTTPException(status_code=404, detail="秘密不存在")
    audit(user["username"], "vault.delete", _target(row))
    return {"ok": True}
