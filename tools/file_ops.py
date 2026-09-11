import os

def read_file(file_path: str) -> str:
    """Read a file from the disk. Never raises — always returns a string,
    including a descriptive error message on failure, since this is called
    as an agent tool and an uncaught exception here would crash the whole
    agent loop rather than just this one tool call."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File {file_path} not found."
        if os.path.isdir(file_path):
            return (
                f"Error: {file_path} is a directory, not a file. "
                f"Use local_list_files to see its contents first."
            )
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {file_path}: {type(e).__name__}: {e}"

def write_file(file_path: str, content: str) -> str:
    """Write content to a file on disk. Never raises."""
    try:
        if os.path.isdir(file_path):
            return f"Error: {file_path} is a directory, not a file. Cannot write to it."
        dirname = os.path.dirname(file_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File {file_path} updated."
    except Exception as e:
        return f"Error writing file {file_path}: {type(e).__name__}: {e}"

def list_files(directory: str) -> str:
    """Recursively list all files in a directory. Never raises."""
    try:
        if not os.path.exists(directory):
            return f"Error: Directory {directory} not found."
        if not os.path.isdir(directory):
            return f"Error: {directory} is a file, not a directory."
        files_list = []
        for root, dirs, files in os.walk(directory):
            # Skip git folder
            if '.git' in dirs:
                dirs.remove('.git')
            if 'node_modules' in dirs:
                dirs.remove('node_modules')
            for file in files:
                files_list.append(os.path.relpath(os.path.join(root, file), directory))
        return "\n".join(files_list) if files_list else "(empty directory)"
    except Exception as e:
        return f"Error listing directory {directory}: {type(e).__name__}: {e}"