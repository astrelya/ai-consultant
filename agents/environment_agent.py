import os
from git import Repo

class EnvironmentAgent:
    def __init__(self):
        self.workspace_dir = os.path.abspath(os.getenv("WORKSPACE_DIR", "./workspaces"))
        os.makedirs(self.workspace_dir, exist_ok=True)

    def prepare_environment(self, story_details: dict) -> dict:
        ticket_id = story_details.get("id", "new_project_repo")
        print(f"  [EnvironmentAgent] Checking environment needs for story: {ticket_id}")
        
        # Parse Repo from ID (e.g. "owner/repo#3")
        github_owner = os.environ.get("GITHUB_OWNER", "your-github-username")
        if "#" in ticket_id:
            full_repo = ticket_id.split("#")[0]  # "astrelya/ao-mail-reader"
        else:
            full_repo = f"{github_owner}/unknown_repo"
            
        repo_name = full_repo.split("/")[-1]
        target_path = os.path.join(self.workspace_dir, repo_name)
        
        # Clone or Pull
        github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN"))
        repo_url = f"https://x-access-token:{github_token}@github.com/{full_repo}.git"
        
        if os.path.exists(target_path):
            print(f"  [EnvironmentAgent] Directory exists. Pulling latest code for {repo_name}...")
            repo = Repo(target_path)
            # Ensure we are on default branch and clean
            repo.git.checkout(repo.remotes.origin.refs[0].name.split('/')[-1])
            repo.remotes.origin.pull()
        else:
            print(f"  [EnvironmentAgent] Cloning {full_repo} to {target_path}...")
            Repo.clone_from(repo_url, target_path)

        return {
            "status": "success",
            "workspace_path": target_path,
            "repo_full_name": full_repo,
            "message": f"Repository {full_repo} prepared at {target_path}"
        }
