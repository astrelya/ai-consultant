import os
import tempfile
import asyncio
import logging

logger = logging.getLogger(__name__)

async def write_spec_file(file_path: str, content: str) -> bool:
    """Writes spec content to the specified file atomically."""
    def _write():
        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            # Create a temporary file in the same directory to ensure rename is atomic
            # and doesn't cross filesystem boundaries
            dir_name = os.path.dirname(file_path) or "."
            fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="spec_", suffix=".tmp")
            
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Atomic rename (on Windows, os.replace replaces existing)
            os.replace(temp_path, file_path)
            return True
        except Exception as e:
            logger.warning(f"Failed to write spec file to {file_path}: {e}")
            # Ensure temp file is cleaned up if rename failed
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass
            return False

    return await asyncio.to_thread(_write)
