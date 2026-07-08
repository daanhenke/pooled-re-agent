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
import sys
import tempfile
import threading
import uuid
from collections.abc import Iterable
from typing import Any, TextIO

from re_agent.llm.protocol import Message


def _feed_stdin(stdin: TextIO, prompt: str) -> None:
    """Write the prompt to the child's stdin and close it (runs on a thread)."""
    try:
        stdin.write(prompt)
        stdin.close()
    except (BrokenPipeError, ValueError, OSError):
        pass


class ClaudeCodeProvider:
    """LLM provider backed by the local ``claude -p`` CLI (subscription creds)."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        timeout_s: int = 1800,
        claude_bin: str = "claude",
        stream: bool = False,
        stream_sink: TextIO | None = None,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._claude_bin = claude_bin
        # When streaming, tee the model's output live to ``stream_sink`` (default
        # stderr) as it arrives, while still capturing it for the return value.
        self._stream = stream
        self._stream_sink = stream_sink
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

        if self._stream:
            return self._send_streaming(cmd, prompt)
        return self._send_buffered(cmd, prompt)

    def _send_buffered(self, cmd: list[str], prompt: str) -> str:
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
            raise RuntimeError(f"claude CLI failed with exit code {proc.returncode}\n{proc.stdout}")
        return proc.stdout.strip()

    def _send_streaming(self, cmd: list[str], prompt: str) -> str:
        """Run claude and tee stdout to the sink as it arrives; return the text."""
        sink = self._stream_sink or sys.stderr
        with tempfile.TemporaryDirectory() as workdir:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # line-buffered
                    cwd=workdir,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"claude CLI not found: {self._claude_bin}") from exc

            assert proc.stdin is not None and proc.stdout is not None
            # Feed the prompt on a separate thread so a large prompt can't
            # deadlock against us reading stdout.
            feeder = threading.Thread(target=_feed_stdin, args=(proc.stdin, prompt), daemon=True)
            feeder.start()
            try:
                output = self._tee_stream(proc.stdout, sink)
                proc.wait(timeout=self._timeout_s)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                raise RuntimeError(f"claude CLI timed out after {self._timeout_s}s") from exc
            finally:
                feeder.join(timeout=5)

        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed with exit code {proc.returncode}\n{output}")
        return output.strip()

    @staticmethod
    def _tee_stream(lines: Iterable[str], sink: TextIO) -> str:
        """Write each chunk to ``sink`` as it arrives and return the full text."""
        chunks: list[str] = []
        for line in lines:
            chunks.append(line)
            sink.write(line)
            sink.flush()
        return "".join(chunks)

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
