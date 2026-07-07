import base64
import os

import requests
from git import Repo
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.tester_agent import _CI_WORKFLOW_TEMPLATE

class EnvironmentAgent:
    def __init__(self):
        self.workspace_dir = os.path.abspath(os.getenv("WORKSPACE_DIR", "./workspaces"))
        os.makedirs(self.workspace_dir, exist_ok=True)
        model_name = os.environ.get("TICKET_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    def _extract_repo_name(self, story_details: dict) -> str:
        ticket_id = story_details.get("id", "")
        ticket_title = story_details.get("title", "")
        ticket_description = story_details.get("description", "")
        
        # If the ticket ID itself contains a repository (e.g. "repo-name#123" or "owner/repo-name#123")
        if ticket_id and "#" in ticket_id:
            repo_part = ticket_id.split("#")[0]
            return repo_part
            
        prompt = f"""
        You are an expert developer.
        Analyze the following ticket details (ID, Title, Description) and extract the name of the GitHub repository associated with this ticket.
        If a repository name is explicitly or implicitly mentioned (e.g. "our appstrelya github repository" or "in repo ao-scraper"), return ONLY the repository name.
        If no repository name is mentioned or it is ambiguous, return "unknown".

        Ticket Details:
        ID: {ticket_id}
        Title: {ticket_title}
        Description: {ticket_description}

        Return ONLY the name of the repository (e.g. "appstrelya" or "ao-scraper"), or "unknown" if not found. Do not include any other text, markdown formatting, or explanation.
        """
        try:
            response = self.llm.invoke(prompt)
            extracted = response.content.strip()
            # Clean up potential markdown formatting or quotes
            extracted = extracted.replace('`', '').replace('"', '').replace("'", '').strip()
            print(f"  [EnvironmentAgent] LLM extracted repo name: '{extracted}'")
            return extracted
        except Exception as e:
            print(f"  [EnvironmentAgent] Error using LLM to extract repository name: {e}")
            return "unknown"

    async def prepare_environment(self, story_details: dict, job_id: str = None, mode: str = None) -> dict:
        ticket_id = story_details.get("id", "new_project_repo")
        print(f"  [EnvironmentAgent] Checking environment needs for story: {ticket_id}")

        agent_mode = mode or os.environ.get("AGENT_MODE", "remote")

        # Resolve the repo name (needed for both modes)
        extracted_repo = self._extract_repo_name(story_details)
        if extracted_repo.lower() == "unknown" or not extracted_repo:
            prompt = f"I could not determine the GitHub repository for ticket **{ticket_id}**. Please enter the repository name (e.g. `appstrelya` or `owner/repo`):"
            if job_id:
                from backend.websocket import broadcast_input_required
                extracted_repo = await broadcast_input_required(prompt, job_id, timeout=120)
            else:
                print(f"\n[Agent]: {prompt}")
                extracted_repo = input("Repository name: ").strip()
            if not extracted_repo:
                return {"status": "failure", "workspace_path": "", "repo_full_name": "", "message": "Repository name was not provided."}

        github_owner = os.environ.get("GITHUB_OWNER", "your-github-username")
        if "/" in extracted_repo:
            full_repo = extracted_repo.split(".git")[0]
            if "github.com/" in full_repo:
                full_repo = full_repo.split("github.com/")[-1]
        else:
            full_repo = f"{github_owner}/{extracted_repo}"

        # In remote mode the developer agent works entirely via GitHub MCP tools.
        # No local clone required.
        if agent_mode == "remote":
            print(f"  [EnvironmentAgent] Remote mode — skipping clone. Repo: {full_repo}")
            return {
                "status": "success",
                "workspace_path": "",
                "repo_full_name": full_repo,
                "message": f"Remote mode: no local clone needed for {full_repo}",
            }

        # Local mode — clone / pull as before
        repo_name = full_repo.split("/")[-1]
        target_path = os.path.join(self.workspace_dir, f"{repo_name}_{ticket_id.replace('/', '-').replace('#', '-')}")
        
        # Clone or Pull
        github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN"))
        repo_url = f"https://x-access-token:{github_token}@github.com/{full_repo}.git"
        
        try:
            if os.path.exists(target_path):
                print(f"  [EnvironmentAgent] Directory exists. Pulling latest code for {repo_name}...")
                repo = Repo(target_path)
                # Fetch first so remote refs are populated (handles local-only repos)
                try:
                    repo.remotes.origin.fetch()
                except Exception:
                    pass
                refs = repo.remotes.origin.refs
                if refs:
                    default_branch = refs[0].name.split('/')[-1]
                else:
                    # No remote refs available — derive from HEAD or fall back
                    try:
                        default_branch = repo.active_branch.name
                    except TypeError:
                        default_branch = "main"
                    print(f"  [EnvironmentAgent] No remote refs found, using branch '{default_branch}'")
                repo.git.checkout(default_branch)
                pull_result = repo.remotes.origin.pull()
                print(f"  [EnvironmentAgent] Pull complete on branch '{default_branch}': {[str(r) for r in pull_result]}")
            else:
                print(f"  [EnvironmentAgent] Cloning {full_repo} to {target_path}...")
                Repo.clone_from(repo_url, target_path)
                print(f"  [EnvironmentAgent] Clone successful.")
        except Exception as e:
            print(f"  [EnvironmentAgent] Git operation failed: {type(e).__name__}: {e}")
            return {
                "status": "failure",
                "workspace_path": "",
                "repo_full_name": full_repo,
                "message": f"Git operation failed: {e}"
            }

        self._ensure_ci_workflow(full_repo, github_token)
        print(f"  [EnvironmentAgent] Workspace ready: {target_path} (repo: {full_repo})")
        return {
            "status": "success",
            "workspace_path": target_path,
            "repo_full_name": full_repo,
            "message": f"Repository {full_repo} prepared at {target_path}"
        }

    def _ensure_ci_workflow(self, repo_full_name: str, github_token: str):
        """Pushes the AI agent test workflow to the repo if it doesn't exist yet."""
        if not github_token:
            print("  [EnvironmentAgent] No GitHub token — skipping CI workflow setup.")
            return
        owner, repo = (repo_full_name.split("/") + ["unknown"])[:2]
        api = "https://api.github.com"
        path = ".github/workflows/ai-tests.yml"
        url = f"{api}/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            get_resp = requests.get(url, headers=headers, timeout=10)
            if get_resp.status_code == 200:
                print(f"  [EnvironmentAgent] CI workflow already exists in {repo_full_name}.")
                return
            encoded = base64.b64encode(_CI_WORKFLOW_TEMPLATE.encode("utf-8")).decode("utf-8")
            payload = {
                "message": "ci: add AI agent test workflow",
                "content": encoded,
            }
            put_resp = requests.put(url, headers=headers, json=payload, timeout=15)
            if put_resp.status_code in (200, 201):
                print(f"  [EnvironmentAgent] CI workflow pushed to {repo_full_name}.")
            else:
                print(f"  [EnvironmentAgent] Failed to push CI workflow: {put_resp.status_code} {put_resp.text[:200]}")
        except Exception as e:
            print(f"  [EnvironmentAgent] Error setting up CI workflow: {e}")

