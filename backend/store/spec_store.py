import logging
from typing import Optional, Dict, Any
from backend.store import database
from backend.store.file_ops import write_spec_file

logger = logging.getLogger(__name__)

async def update_project_spec(project_id: str, spec_content: str, repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Updates the spec for a project in the database and optionally writes it to a file.
    """
    pool = database.get_pool()
    query = "UPDATE projects SET spec = $1, updated_at = NOW() WHERE id = $2 RETURNING spec, updated_at"
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, spec_content, project_id)
        
        if not row:
            # If project doesn't exist, we don't proceed with file writing
            return {}

        result = {
            "spec": row["spec"],
            "updated_at": row["updated_at"],
            "spec_file_written": False,
            "spec_file_path": None
        }

        if repo_path:
            import os
            spec_file_path = os.path.join(repo_path, "spec.md")
            # Replace backslashes with forward slashes for cross-platform consistency if desired, 
            # or just rely on os.path.join.
            success = await write_spec_file(spec_file_path, spec_content)
            
            if success:
                result["spec_file_written"] = True
                result["spec_file_path"] = spec_file_path
            else:
                logger.warning(f"Database updated for {project_id} but failed to write spec file.")
                
        return result
