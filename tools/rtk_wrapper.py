import os
import shutil
import subprocess

def run_command_with_rtk(cmd: list, cwd: str = None, timeout: int = 120) -> tuple:
    """
    Executes a shell command. If 'rtk' is installed in the system PATH,
    the command is run through 'rtk <command>' to compress and summarize
    the terminal output for the LLM. Otherwise, runs the command normally.
    
    Returns:
        tuple: (passed: bool, stdout: str, stderr: str)
    """
    # Check if rtk is installed
    rtk_path = shutil.which("rtk") or shutil.which("rtk.exe")
    
    modified_cmd = cmd.copy()
    if rtk_path:
        print(f"[RTK Wrapper] Found rtk at: {rtk_path}. Prepending to command.")
        modified_cmd = [rtk_path] + modified_cmd
    else:
        print(f"[RTK Wrapper] rtk not found in PATH. Running command normally: {cmd}")

    try:
        # Run subprocess
        result = subprocess.run(
            modified_cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout} seconds."
    except Exception as e:
        return False, "", f"Command execution failed: {e}"
