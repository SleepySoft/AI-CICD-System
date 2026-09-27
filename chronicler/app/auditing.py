"""结构化操作审计：只接受调用方明确选择的非秘密元数据。"""
import contextvars
import functools
import hashlib
import inspect
import json
import uuid
from contextlib import contextmanager

_context = contextvars.ContextVar("audit_context", default={})


def context():
    return dict(_context.get())


@contextmanager
def scope(**fields):
    token = _context.set({**context(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def record(action, target="", *, result="success", actor=None, **detail):
    from . import db
    ctx = context()
    payload = {**{k: v for k, v in ctx.items() if k != "actor"}, **detail, "result": result}
    db.audit(actor or ctx.get("actor", "system"), action, target,
             json.dumps(payload, ensure_ascii=False, sort_keys=True))


@contextmanager
def stage(action, target="", **detail):
    record(action, target, result="started", **detail)
    outcome = {"result": "success"}
    try:
        yield outcome
    except Exception as exc:
        # 异常文本可能包含 hook 输出、连接串和秘密，只记录类型。
        record(action, target, result="failed", error_class=type(exc).__name__, **detail)
        raise
    else:
        record(action, target, **detail, **outcome)


def operation(action, source=None):
    def decorate(fn):
        signature = inspect.signature(fn)
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            from . import db
            db.init()
            params = signature.bind(*args, **kwargs).arguments
            fields = {"correlation_id": context().get("correlation_id") or uuid.uuid4().hex,
                      "actor": context().get("actor") or params.get("actor", "system")}
            if source:
                fields.update(source=source, consumer=context().get("source", "system"))
            with scope(**fields):
                with stage(action):
                    return fn(*args, **kwargs)
        return wrapped
    return decorate


def vault_mutation(kind):
    """存储层逐项记录，覆盖 API、配置同步和导入；指纹基于密文，避免猜测弱密码。"""
    def decorate(fn):
        signature = inspect.signature(fn)
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            from .vault import store
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            params = bound.arguments
            before = store.get_row(params["sid"]) if "sid" in params else None
            target = (f"{before['scope']}/{before['name']}" if before else
                      f"{params.get('scope', '')}/{params.get('name', '')}" if "scope" in params
                      else f"secret#{params['sid']}")
            actor = context().get("actor") or params.get("actor", "system")
            def revision(row):
                return hashlib.sha256(row["ciphertext"]).hexdigest() if row else None
            detail = {"before_revision": revision(before)}
            if kind == "metadata":
                detail["fields"] = sorted(set(params["fields"]) &
                                          {"summary", "owner", "expires_at", "secret_type", "rotation_risk"})
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                record(f"vault.mutation.{kind}", target, actor=actor, result="failed",
                       error_class=type(exc).__name__, **detail)
                raise
            after = store.get_row(result if kind == "create" else params["sid"])
            detail["after_revision"] = revision(after)
            if kind == "metadata":
                detail["changed_fields"] = [k for k in detail["fields"]
                                           if before and after and before[k] != after[k]]
            record(f"vault.mutation.{kind}", target, actor=actor,
                   result="unchanged" if before == after else "success", **detail)
            return result
        return wrapped
    return decorate
