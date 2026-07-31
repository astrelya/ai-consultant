"""
SubprocessRunner — async subprocess wrapper that bridges stdout/stderr to the SSE stream.

Architecture decision (AD-11, AD-9):
- Use asyncio.create_subprocess_exec() only — never subprocess.run() or Popen().
- Each stdout line is forwarded via publish_event() immediately (AD-7: streaming over polling).
- SubprocessRunner does NOT need to be a singleton (unlike MCPManager).
"""
import asyncio
import shlex

from backend.api.sse import publish_event


class SubprocessRunner:
    """Launch a shell command asynchronously and stream its output to the project's SSE channel."""

    @staticmethod
    async def run(cmd: str, project_id: str) -> int:
        """Launch *cmd* as an async subprocess and bridge output to the project SSE channel.

        Args:
            cmd: Shell command string (e.g. ``"echo hello"``).
            project_id: Project identifier used to route SSE events.

        Returns:
            The subprocess exit code.

        Events published:
            - ``bmad_output``   — one per stdout line, payload ``{"line": str}``
            - ``bmad_complete`` — on exit, payload ``{"exit_code": int}``
            - ``bmad_error``    — on non-zero exit, payload ``{"exit_code": int, "stderr": str}``
        """
        # Split command safely; shlex.split handles quoted args correctly.
        args = shlex.split(cmd)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # --- Stream stdout line-by-line (AD-7: no buffering until completion) ---
        assert proc.stdout is not None  # guaranteed when PIPE is used
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line_str = raw.decode("utf-8").rstrip("\n")
            await publish_event(project_id, "bmad_output", {"line": line_str})

        # Wait for process to finish and collect exit code
        exit_code = await proc.wait()

        # Drain remaining stderr (collected but not streamed per story spec)
        assert proc.stderr is not None
        stderr_bytes = await proc.stderr.read()
        stderr_content = stderr_bytes.decode("utf-8")

        # --- Publish completion events ---
        await publish_event(project_id, "bmad_complete", {"exit_code": exit_code})
        if exit_code != 0:
            await publish_event(
                project_id,
                "bmad_error",
                {"exit_code": exit_code, "stderr": stderr_content},
            )

        return exit_code
