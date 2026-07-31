import asyncio
import sys
import os

from backend.api.sse import publish_event

async def run_brainstorm_pipeline(project_id: str, user_input: str) -> dict:
    """
    Launches the BMad brainstorm subprocess and streams stdout to SSE channel.
    """
    cmd = [
        sys.executable, "-m", "bmad", "brainstorm",
        "--project-id", project_id,
        "--input", user_input
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ
        )
        
        spec_content = []
        
        if process.stdout:
            async for line in process.stdout:
                decoded_line = line.decode('utf-8').strip()
                await publish_event(project_id, "bmad_output", {"line": decoded_line})
                spec_content.append(decoded_line)
                
        stderr_content = b""
        if process.stderr:
            stderr_content = await process.stderr.read()
            
        await process.wait()
        
        if process.returncode == 0:
            return {
                "exit_code": 0,
                "complete": True,
                "spec_content": "\n".join(spec_content)
            }
        else:
            return {
                "exit_code": process.returncode,
                "complete": False,
                "error": stderr_content.decode('utf-8')
            }
            
    except Exception as e:
        return {
            "exit_code": -1,
            "complete": False,
            "error": str(e)
        }


async def run_spec_review_pipeline(project_id: str, spec_input: str) -> dict:
    """
    Launches the BMad spec validation subprocess and streams stdout to SSE channel.

    Streams each stdout line as a ``bmad_output`` SSE event.
    Returns a dict with ``exit_code``, ``complete``, and ``spec_content`` on success
    or ``error`` on failure.

    Architecture constraints (AD-7, AD-9, AD-11):
    - Non-blocking: subprocess is async.
    - Streaming: each stdout line is published immediately.
    """
    cmd = [
        sys.executable, "-m", "bmad", "validate",
        "--project-id", project_id,
        "--input", spec_input
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ,
        )

        output_lines: list[str] = []

        if process.stdout:
            async for raw_line in process.stdout:
                decoded = raw_line.decode("utf-8").rstrip("\n")
                await publish_event(project_id, "bmad_output", {"line": decoded})
                output_lines.append(decoded)

        stderr_content = b""
        if process.stderr:
            stderr_content = await process.stderr.read()

        await process.wait()

        if process.returncode == 0:
            return {
                "exit_code": 0,
                "complete": True,
                "spec_content": "\n".join(output_lines),
            }
        else:
            return {
                "exit_code": process.returncode,
                "complete": False,
                "error": stderr_content.decode("utf-8"),
            }

    except Exception as exc:
        return {
            "exit_code": -1,
            "complete": False,
            "error": str(exc),
        }
