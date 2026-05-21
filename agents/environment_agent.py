import os
from git import Repo
from langchain_google_genai import ChatGoogleGenerativeAI

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
            return extracted
        except Exception as e:
            print(f"  [EnvironmentAgent] Error using LLM to extract repository name: {e}")
            return "unknown"

    def prepare_environment(self, story_details: dict) -> dict:
        ticket_id = story_details.get("id", "new_project_repo")
        print(f"  [EnvironmentAgent] Checking environment needs for story: {ticket_id}")
        
        extracted_repo = self._extract_repo_name(story_details)
        
        # If unknown, ask user
        if extracted_repo.lower() == "unknown" or not extracted_repo:
            print(f"\n[Agent]: I could not determine the GitHub repository for ticket {ticket_id} from the ticket details.")
            user_input = input("Please enter the repository name (e.g. 'appstrelya' or 'owner/repo'): ").strip()
            if user_input:
                extracted_repo = user_input
            else:
                return {
                    "status": "failure",
                    "workspace_path": "",
                    "repo_full_name": "",
                    "message": "Repository name was not provided."
                }
        
        # Parse Repo from the extracted string
        github_owner = os.environ.get("GITHUB_OWNER", "your-github-username")
        if "/" in extracted_repo:
            full_repo = extracted_repo.split(".git")[0]
            if "github.com/" in full_repo:
                full_repo = full_repo.split("github.com/")[-1]
        else:
            full_repo = f"{github_owner}/{extracted_repo}"
            
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

