"""Agent 注册表（agents.yaml）加载 + 安装状态探测 + 会话参数组装

M1.5 过渡形态：注册表为 YAML 文件（只读挂载热更新），字段对齐
docs/what/manager.md §2.1 的 agent_profile 契约，M2 迁移 Postgres。
密钥安全（NFR-002）：api_key_ref 只存环境变量名，解析发生在创建会话时，
注册表与 API 响应均不含密钥明文。
"""
import os
from pathlib import Path

import yaml
from fastapi import HTTPException

from .config import Cfg

# 创建 ATR 会话时按 cli_type 注入的密钥环境变量名（值来自 api_key_ref 指向的 Manager 环境变量）
KEY_ENV_BY_CLI_TYPE = {
    "aider": "OPENAI_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}
DEFAULT_KEY_ENV = "LLM_API_KEY"


def load_agents() -> list[dict]:
    with open(Cfg.AGENTS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)["agents"]


def get_agent(name: str) -> dict:
    agent = next((a for a in load_agents() if a["name"] == name), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"未知 agent：{name}")
    return agent


def agent_status(name: str) -> dict:
    """探测持久卷中的安装状态（VERSION 文件由 scripts/agents/<name>.sh 写入）"""
    version_file = Path(Cfg.AGENTS_ROOT) / name / "VERSION"
    if version_file.is_file():
        return {"installed": True, "version": version_file.read_text(encoding="utf-8").strip()}
    return {"installed": False, "version": None}


def list_agents() -> list[dict]:
    """注册表 + 安装状态；绝不返回密钥明文（api_key_ref 只回传引用名）"""
    return [{**a, **agent_status(a["name"])} for a in load_agents()]


def build_session_payload(agent: dict) -> dict:
    """按注册表组装 ATR 会话参数：command + env（HOME/PATH/静态 env/密钥注入）"""
    name = agent["name"]
    prefix = f"/opt/agents/{name}"
    env = {
        "HOME": prefix,  # 登录态随持久卷保留（ADR-0017）
        "PATH": f"{prefix}/bin:/usr/local/bin:/usr/bin:/bin",
        **{k: str(v) for k, v in (agent.get("env") or {}).items()},
    }
    key_ref = agent.get("api_key_ref")
    if key_ref:
        value = os.environ.get(key_ref, "")
        if value:
            env[KEY_ENV_BY_CLI_TYPE.get(agent.get("cli_type"), DEFAULT_KEY_ENV)] = value
    command = agent["command"]
    if agent.get("extra_args"):
        command = f"{command} {agent['extra_args']}"
    return {"command": command, "env": env}
