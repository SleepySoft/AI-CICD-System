"""秘密库 API（admin 专属；FR-INIT-013/014/015/016 一期形态）

元数据透明：列表/详情永不含秘密值；值只在显式 reveal/download/export 时解密，全部写审计。
"""
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth import require_admin
from ..db import audit, q
from ..vault import crypto, exporter, store, sync

router = APIRouter(prefix="/api/vault", tags=["vault"], dependencies=[Depends(require_admin)])

_MAX_SIZE = 10 * 1024 * 1024  # 单条秘密/文件上限 10MB


def _guard():
    """锁定守卫：库非空而主密钥缺失/不匹配时拒绝写入与解密（docs/how/secrets-vault.md §3.5）。"""
    try:
        store._identity_verified()
    except store.VaultLocked as e:
        raise HTTPException(status_code=409,
                            detail=f"秘密库已锁定：{e}。请先用原主密钥解锁；"
                                   "若确要放弃旧数据，请在程序外清理后再重启。")


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


class KeyBody(BaseModel):
    key: str


class ImportBody(BaseModel):
    force: bool = False


def _load_components() -> dict:
    from ..initialization import catalog
    return catalog.load()


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


@router.get("/status")
def status():
    """锁定/交接状态（资源透明：数量与状态可见，不含值）。"""
    return store.lock_state()


@router.post("/unlock")
def unlock(body: KeyBody, user: dict = Depends(require_admin)):
    """收养 admin 提交的主密钥：抽样解密验证通过后落盘（docs/how/secrets-vault.md §3.5）。"""
    try:
        recipient = store.try_unlock(body.key)
    except ValueError as e:
        audit(user["username"], "vault.unlock_failed", "", "")
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.unlock", "", "")
    return {"ok": True, "recipient": recipient}


@router.post("/master/ack")
def master_ack(body: KeyBody, user: dict = Depends(require_admin)):
    """主密钥交接确认：admin 粘贴回主密钥证明已收存（prove possession）。"""
    if not store.ack_key(body.key):
        raise HTTPException(status_code=400, detail="与当前主密钥不一致，请核对后重试")
    audit(user["username"], "vault.key_acked", "", "")
    return {"ok": True}


@router.post("/import-env")
def import_env(body: ImportBody, user: dict = Depends(require_admin)):
    """把 .env 中已配置的组件秘密导入 vault（老系统接管；冲突默认不覆盖）。"""
    _guard()
    return sync.import_env(_load_components(), actor=user["username"], force=body.force)


@router.get("/env-status")
def env_status():
    """漂移检测（只读）：.env 与 vault 双向比对，基于明文 sha256，不泄露值。"""
    return sync.env_status(_load_components())


@router.post("/import-export")
async def import_export(user: dict = Depends(require_admin),
                        file: UploadFile = File(...), force: bool = Form(False)):
    """从导出包恢复秘密（新部署/灾难恢复）；冲突默认不覆盖。"""
    _guard()
    data = await file.read()
    try:
        result = exporter.restore_export(data, actor=user["username"], force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.import_export", "",
          f"imported={result['imported']} skipped={result['skipped']} "
          f"conflicts={len(result['conflicts'])} force={force}")
    return result


@router.get("/export")
def export_all(user: dict = Depends(require_admin)):
    """全量导出：明文 manifest + age 密文负载（ADR-0041）。"""
    _guard()
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
    _guard()
    identity = crypto.load_identity()
    audit(user["username"], "vault.master_reveal")
    return {"secret": str(identity)}


@router.post("/text")
def create_text(body: TextBody, user: dict = Depends(require_admin)):
    _guard()
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
    _guard()
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
    _guard()
    row = _get_or_404(sid)
    if row["kind"] != "text":
        raise HTTPException(status_code=400, detail="文件型秘密请用下载")
    audit(user["username"], "vault.reveal", _target(row))
    return Response(content=store.decrypt_value(row), media_type="text/plain; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@router.get("/{sid:int}/download")
def download(sid: int, user: dict = Depends(require_admin)):
    _guard()
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
    _guard()
    row = _get_or_404(sid)
    if row["kind"] != "text":
        raise HTTPException(status_code=400, detail="文件型秘密请删除后重新上传")
    try:
        store.replace_value(sid, body.value.encode("utf-8"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(user["username"], "vault.rotate", _target(row), f"rotation_risk={row['rotation_risk']}")
    return {"ok": True}


@router.get("/propagation")
def propagation_pending():
    """待传播清单：vault 变更尚未落到组件的秘密（维护横幅数据源）。
    hint 按秘密类型与组件能力生成：账号型→重置密码能力直写；client-secret→重部署+OIDC 对齐；
    其余注入型→重新部署（compose 配置哈希收敛，仅变化的容器重建）。"""
    from pathlib import Path

    from ..initialization import catalog
    comps = {name: entry["component"] for name, entry in catalog.load().items()
             if not entry.get("error")}
    items = []
    for scope, entry in sorted(store.pending_propagation().items(), key=lambda kv: -kv[1]["at"]):
        items.append({"scope": scope, "keys": entry["keys"], "at": entry["at"],
                      "hint": _propagation_hint(scope, entry["keys"], comps.get(scope))})
    return {"pending": items}


def _propagation_hint(scope: str, keys: list, comp: dict | None) -> str:
    from pathlib import Path
    if scope == "infra":
        return "Chronicler 自身秘密：重启 supervisor 生效"
    if not comp:
        return "组件未注册；若为已移除组件可消除标记"
    fields = {f.get("key"): f for f in comp.get("fields") or []}
    types = {fields[k].get("secret_type") for k in keys if k in fields}
    comp_dir = Path(comp.get("_dir", ""))
    has_users_hook = (comp_dir / "hooks" / "users.py").is_file()
    if types & {"client-secret"}:
        return "重新部署该组件，并重跑身份组件「OIDC 客户端注册」能力对齐两端"
    if types and types <= {"password", "access-key"} and has_users_hook:
        return "账号型秘密：用组件「重置密码」能力直写组件，无需重启"
    return "重新部署组件生效（工具面板「部署」；仅配置变化的容器会重建）"


@router.post("/propagation/{scope}/dismiss")
def propagation_dismiss(scope: str, user: dict = Depends(require_admin)):
    """人工确认已对齐（如手工在组件侧改好）后消除标记；写审计。"""
    store.clear_pending(scope, actor=user["username"])
    return {"ok": True}


@router.delete("/{sid:int}")
def delete_secret(sid: int, user: dict = Depends(require_admin)):
    row = store.delete(sid)
    if not row:
        raise HTTPException(status_code=404, detail="秘密不存在")
    audit(user["username"], "vault.delete", _target(row))
    return {"ok": True}
