import os

def read_file(file_path: str) -> str:
    """Read a file from the disk."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(file_path: str, content: str) -> str:
    """Write content to a file on disk."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Success: File {file_path} updated."

def list_files(directory: str) -> str:
    """Recursively list all files in a directory."""
    if not os.path.exists(directory):
        return f"Error: Directory {directory} not found."
    files_list = []
    for root, dirs, files in os.walk(directory):
        # Skip git folder
        if '.git' in dirs:
            dirs.remove('.git')
        for file in files:
            files_list.append(os.path.relpath(os.path.join(root, file), directory))
    return "\n".join(files_list)
