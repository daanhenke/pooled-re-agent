"""Claude Code CLI-backed LLM provider using subscription credentials.

Mirrors :class:`re_agent.llm.codex_cli.CodexCLIProvider`: it shells out to the
local ``claude`` CLI in non-interactive print mode, so it uses the user's logged
-in Claude Code credentials (subscription/OAuth) and needs **no API key**.

The prompt is fed on stdin (decompiled listings can be large), and the CLI runs
in a throwaway working directory.  ``--bare`` is intentionally *not* used because
it forces ``ANTHROPIC_API_KEY`` auth and ignores the OAuth/keychain login.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any

from re_agent.llm.protocol import Message


class ClaudeCodeProvider:
    """LLM provider backed by the local ``claude -p`` CLI (subscription creds)."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        timeout_s: int = 1800,
        claude_bin: str = "claude",
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._claude_bin = claude_bin
        self._conversations: dict[str, list[Message]] = {}

    def send(self, messages: list[Message], **kwargs: Any) -> str:
        prompt = self._render_messages(messages)
        model = kwargs.get("model", self._model)

        cmd = [self._resolve_bin(), "--print", "--output-format", "text"]
        if model:
            cmd += ["--model", str(model)]
        # Non-interactive runs auto-deny approval-gated tools, but pin it down
        # anyway: this is pure text generation, no editing/execution wanted.
        cmd += ["--disallowedTools", "Bash Edit Write NotebookEdit"]

        with tempfile.TemporaryDirectory() as workdir:
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=self._timeout_s,
                    check=False,
                    cwd=workdir,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"claude CLI timed out after {self._timeout_s}s") from exc
            except FileNotFoundError as exc:
                raise RuntimeError(f"claude CLI not found: {self._claude_bin}") from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed with exit code {proc.returncode}\n{proc.stdout}"
            )
        return proc.stdout.strip()

    def _resolve_bin(self) -> str:
        """Resolve the claude executable, preferring a launcher CreateProcess can run.

        On Windows a bare ``claude`` on PATH is the git-bash shell shim (no
        extension), which CreateProcess rejects; prefer ``claude.cmd``/``.exe``.
        """
        if os.name == "nt":
            for ext in (".cmd", ".exe", ".bat"):
                cand = shutil.which(self._claude_bin + ext)
                if cand:
                    return cand
        return shutil.which(self._claude_bin) or self._claude_bin

    @property
    def supports_conversations(self) -> bool:
        return True

    def new_conversation(self, system: str) -> str:
        cid = uuid.uuid4().hex
        self._conversations[cid] = [Message(role="system", content=system)]
        return cid

    def resume(self, conversation_id: str, message: str) -> str:
        history = self._conversations.get(conversation_id)
        if history is None:
            raise KeyError(f"Unknown conversation ID: {conversation_id}")

        history.append(Message(role="user", content=message))
        response_text = self.send(list(history))
        history.append(Message(role="assistant", content=response_text))
        return response_text

    @staticmethod
    def _render_messages(messages: list[Message]) -> str:
        parts: list[str] = []
        for msg in messages:
            role = msg.role.upper()
            parts.append(f"[{role}]\n{msg.content.strip()}")
        return "\n\n".join(parts).strip()
