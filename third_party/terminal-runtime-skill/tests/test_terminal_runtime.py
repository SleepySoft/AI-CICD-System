"""System/behaviour tests for terminal_runtime_service.py.

These tests import the service module directly and exercise the platform-
independent logic (encoding, mode tracking, state detection, locks).  They do
not start a real PTY and therefore run on any platform.
"""

from __future__ import annotations

import pytest

from scripts.terminal_runtime_service import (
    CreateSessionRequest,
    TerminalSession,
    ctrl_key,
    is_dangerous_text,
)


# -----------------------------------------------------------------------------
# Encoding helpers
# -----------------------------------------------------------------------------

def test_ctrl_key_basic():
    assert ctrl_key("CTRL_C") == b"\x03"
    assert ctrl_key("ctrl-a") == b"\x01"
    assert ctrl_key("CTRL_Z") == b"\x1a"


def test_ctrl_key_invalid():
    with pytest.raises(ValueError):
        ctrl_key("CTRL")
    with pytest.raises(ValueError):
        ctrl_key("CTRL_1")


def test_encode_text_action():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    action = s._encode_action.__self__  # noqa: SLF001
    # Use the public-ish method directly via the instance.
    from scripts.terminal_runtime_service import TerminalAction

    assert s._encode_action(TerminalAction(type="text", text="hello")) == "hello"  # noqa: SLF001


def test_encode_submit_action():
    from scripts.terminal_runtime_service import TerminalAction

    s = TerminalSession(CreateSessionRequest(command="bash"))
    assert s._encode_action(TerminalAction(type="submit", text="ls")) == "ls\r"  # noqa: SLF001


def test_encode_paste_without_bracketed_paste():
    from scripts.terminal_runtime_service import TerminalAction

    s = TerminalSession(CreateSessionRequest(command="bash"))
    assert s._encode_action(TerminalAction(type="paste", text="hello")) == "hello"  # noqa: SLF001


def test_encode_paste_with_bracketed_paste():
    from scripts.terminal_runtime_service import TerminalAction

    s = TerminalSession(CreateSessionRequest(command="bash"))
    s.modes.bracketed_paste = True
    assert s._encode_action(TerminalAction(type="paste", text="hello")) == "\x1b[200~hello\x1b[201~"  # noqa: SLF001


def test_encode_key_arrows():
    from scripts.terminal_runtime_service import TerminalAction

    s = TerminalSession(CreateSessionRequest(command="bash"))
    assert s._encode_action(TerminalAction(type="key", key="UP")) == "\x1b[A"  # noqa: SLF001
    s.modes.application_cursor_keys = True
    assert s._encode_action(TerminalAction(type="key", key="UP")) == "\x1bOA"  # noqa: SLF001


def test_encode_key_control():
    from scripts.terminal_runtime_service import TerminalAction

    s = TerminalSession(CreateSessionRequest(command="bash"))
    assert s._encode_action(TerminalAction(type="control", key="CTRL_D")) == "\x04"  # noqa: SLF001


# -----------------------------------------------------------------------------
# Security helpers
# -----------------------------------------------------------------------------

def test_is_dangerous_text_detects_sudo():
    assert is_dangerous_text("sudo rm -rf /") is not None


def test_is_dangerous_text_allows_safe():
    assert is_dangerous_text("ls -la") is None


# -----------------------------------------------------------------------------
# Mode tracking
# -----------------------------------------------------------------------------

def test_track_application_cursor_keys():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    changed = s._track_modes("\x1b[?1h")  # noqa: SLF001
    assert ("application_cursor_keys", True) in changed
    assert s.modes.application_cursor_keys is True


def test_track_bracketed_paste():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    changed = s._track_modes("\x1b[?2004h")  # noqa: SLF001
    assert ("bracketed_paste", True) in changed


def test_track_no_duplicate_events():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    s._track_modes("\x1b[?1h")  # noqa: SLF001
    changed = s._track_modes("\x1b[?1h")  # noqa: SLF001
    assert changed == []


# -----------------------------------------------------------------------------
# State detection
# -----------------------------------------------------------------------------

def test_detect_shell_prompt():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    text = "user@host:~$"
    lines = [text]
    detected = s._detected_state_locked(text, lines, 1000)  # noqa: SLF001
    assert detected["prompt_likely"] is True
    assert detected["shell_prompt_likely"] is True
    assert detected["input_readiness"]["status"] == "likely_ready"


def test_detect_confirmation():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    text = "Are you sure? [Y/n]"
    detected = s._detected_state_locked(text, [text], 1000)  # noqa: SLF001
    assert detected["confirmation_likely"] is True


def test_detect_error():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    text = "Traceback (most recent call last): error happened"
    detected = s._detected_state_locked(text, [text], 0)  # noqa: SLF001
    assert detected["error_likely"] is True


def test_detect_tui():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    s.modes.alternate_screen = True
    detected = s._detected_state_locked("menu", ["menu"], 1000)  # noqa: SLF001
    assert detected["tui_likely"] is True


# -----------------------------------------------------------------------------
# Locks
# -----------------------------------------------------------------------------

def test_acquire_and_release_lock():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    result = s.acquire_lock("alice", lease_ms=10000)
    assert result["ok"] is True
    assert s.session_lock.active() is True

    token = result["lock_token"]
    result = s.release_lock("alice", token)
    assert result["released"] is True
    assert s.session_lock.active() is False


def test_other_actor_blocked_without_force():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    s.acquire_lock("alice", lease_ms=10000)
    with pytest.raises(PermissionError):
        s.acquire_lock("bob", lease_ms=10000)


def test_force_take_lock():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    s.acquire_lock("alice", lease_ms=10000)
    result = s.acquire_lock("bob", lease_ms=10000, force=True)
    assert result["ok"] is True
    assert s.session_lock.actor == "bob"


# -----------------------------------------------------------------------------
# tmux persistence backend (pure logic; no tmux binary required)
# -----------------------------------------------------------------------------

def test_tmux_session_name_sanitizes():
    from scripts.terminal_runtime_service import tmux_session_name, TMUX_PREFIX

    assert tmux_session_name("kimi-main") == TMUX_PREFIX + "kimi-main"
    # '.' and ':' are special in tmux target syntax and must be folded
    name = tmux_session_name("agent:01.dev")
    assert name == TMUX_PREFIX + "agent-01-dev"
    assert ":" not in name and "." not in name
    # empty-after-sanitize still yields a usable name
    assert tmux_session_name("...").startswith(TMUX_PREFIX)


def test_tmux_command_string():
    from scripts.terminal_runtime_service import tmux_command_string

    assert tmux_command_string("kimi --flag", shell=False) == "kimi --flag"
    assert tmux_command_string(["python3", "a b.py"], shell=False) == "python3 'a b.py'"


def test_build_tmux_client_argv_create():
    from scripts.terminal_runtime_service import build_tmux_client_argv

    argv = build_tmux_client_argv(
        "atr-demo",
        create=True,
        command=["vim", "my file.txt"],
        cwd="/work",
        env={"FOO": "bar"},
        rows=40,
        cols=120,
    )
    assert argv[:2] == ["tmux", "-2"]
    assert "new-session" in argv
    assert argv[argv.index("-s") + 1] == "atr-demo"
    assert argv[argv.index("-x") + 1] == "120"
    assert argv[argv.index("-y") + 1] == "40"
    assert argv[argv.index("-c") + 1] == "/work"
    assert "FOO=bar" in argv
    assert argv[-2] == "--"
    assert argv[-1] == "vim 'my file.txt'"


def test_build_tmux_client_argv_attach():
    from scripts.terminal_runtime_service import build_tmux_client_argv

    argv = build_tmux_client_argv("atr-demo", create=False)
    assert argv == ["tmux", "-2", "attach-session", "-t", "atr-demo"]


def test_parse_tmux_list_filters_prefix():
    from scripts.terminal_runtime_service import parse_tmux_list

    output = (
        "atr-kimi\tkimi\t/home/atr\t1720000000\n"
        "other\tbash\t/home/atr\t1720000001\n"
        "malformed-line\n"
    )
    sessions = parse_tmux_list(output, "atr-")
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_id"] == "kimi"
    assert s["command"] == "kimi"
    assert s["cwd"] == "/home/atr"
    assert s["created_at"] == 1720000000.0


def test_session_backend_defaults_and_tmux_name():
    s = TerminalSession(CreateSessionRequest(command="bash"))
    assert s.backend == "pty"
    assert s.tmux_name is None

    s2 = TerminalSession(CreateSessionRequest(command="kimi", id="my.agent", backend="tmux"))
    assert s2.backend == "tmux"
    assert s2.tmux_name == "atr-my-agent"
    # tmux liveness is only meaningful for tmux sessions
    assert s._tmux_session_alive() is None  # noqa: SLF001


def test_ensure_flag_defaults_false():
    req = CreateSessionRequest(command="bash")
    assert req.ensure is False
    req2 = CreateSessionRequest(command="bash", ensure=True)
    assert req2.ensure is True


# -----------------------------------------------------------------------------
# Remote-listen security gate
# -----------------------------------------------------------------------------

def test_insecure_listen_gate():
    from scripts.terminal_runtime_service import insecure_listen_reason

    # loopback without token is fine
    assert insecure_listen_reason("127.0.0.1", "", False) is None
    assert insecure_listen_reason("localhost", "", False) is None
    # public bind without token is refused
    assert insecure_listen_reason("0.0.0.0", "", False) is not None
    # token or explicit override allows it
    assert insecure_listen_reason("0.0.0.0", "secret", False) is None
    assert insecure_listen_reason("0.0.0.0", "", True) is None
