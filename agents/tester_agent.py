"""
Tester Agent Module
Responsible for generating unit tests for the code created by the Developer Agent.
"""
import os
import subprocess
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from tools.file_ops import read_file

class TesterAgent:
    def __init__(self):
        model_name = os.getenv("CODING_MODEL", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(model=model_name)

    def write_and_run_tests(self, story_details: dict, code_files: list, workspace_path: str) -> dict:
        print(f"  [TesterAgent] Analyzing files for testing: {code_files}")
        
        test_files = []
        for file in code_files:
            file_name = os.path.basename(file)
            test_file_path = os.path.join(workspace_path, "tests", f"test_{file_name}")
            os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
            
            # Read the content of the implemented code file
            code_content = read_file(file)
            
            # Generate tests using LLM
            system_prompt = (
                "You are an expert Python tester. Your task is to write meaningful pytest unit tests "
                "for the provided Python code. Ensure the tests cover the main functionality and edge cases. "
                "Output ONLY the Python code for the tests, without any markdown formatting or explanations."
            )
            
            user_prompt = (
                f"Here is the code for {file_name}:\n\n"
                f"```python\n{code_content}\n```\n\n"
                f"Please write pytest unit tests for this code."
            )
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            test_code = response.content.strip()
            
            # Remove markdown code blocks if present
            if test_code.startswith("```python"):
                test_code = test_code[9:]
            elif test_code.startswith("```"):
                test_code = test_code[3:]
            if test_code.endswith("```"):
                test_code = test_code[:-3]
            test_code = test_code.strip()
            
            with open(test_file_path, "w") as f:
                f.write(test_code)
            
            test_files.append(test_file_path)
            print(f"  [TesterAgent] Created test file: {test_file_path}")
            
        print("  [TesterAgent] Running tests...")
        
        # Execute tests via subprocess (pytest)
        tests_dir = os.path.join(workspace_path, "tests")
        try:
            result = subprocess.run(
                ["pytest", tests_dir],
                capture_output=True,
                text=True,
                check=False
            )
            
            status = "success" if result.returncode == 0 else "failure"
            output = result.stdout + "\n" + result.stderr
            
            return {
                "status": status,
                "test_files": test_files,
                "output": output,
                "message": f"Tests completed with status: {status}"
            }
        except Exception as e:
            return {
                "status": "failure",
                "test_files": test_files,
                "output": str(e),
                "message": "Failed to execute tests."
            }
