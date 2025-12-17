from typing import List, Dict, Optional, Any
import os
import re
import shutil
import git
from core.chat_interface import ChatInterface
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

class SastAgent(ChatInterface):
    """SAST Agent for static application security testing."""

    def __init__(self):
        self.llm = None # Placeholder for potential LLM integration
        # Other SAST tool specific initializations can go here
    
    def initialize(self) -> None:
        """Initialize components for the SAST agent."""
        print("SAST Agent initialized.")
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    def process_message(self, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Process a message and perform SAST analysis on a GitHub repository.
        
        Args:
            message: The message containing the GitHub repository URL.
            chat_history: Optional chat history.
            
        Returns:
            str: A response indicating the result of the SAST analysis.
        """
        print(f"Received message for SAST analysis: {message}")

        # Extract GitHub URL from the message
        github_url_match = re.search(r"https://github.com/[a-zA-Z0-9\-_]+/[a-zA-Z0-9\-_]+", message)
        if not github_url_match:
            return "Please provide a valid GitHub repository URL."

        github_url = github_url_match.group(0)
        repo_name = github_url.split("/")[-1]
        clone_dir = os.path.join("/tmp", repo_name)

        # Clone the repository
        try:
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)
            git.Repo.clone_from(github_url, clone_dir)
        except Exception as e:
            return f"Error cloning the repository: {e}"

        vulnerabilities = []
        file_count = 0
        file_limit = 10  # Changed from 5 to 10
        # Walk through the repository and analyze files
        for root, dirs, files in os.walk(clone_dir):
            if file_count >= file_limit:
                break
            for file in files:
                if file_count >= file_limit:
                    break
                # Add file extensions you want to scan
                if file.endswith((".py", ".java", ".js", ".php", ".html", ".sql")):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    # Create a prompt for the LLM
                    prompt = f"""
                    Analyze the following code for SQL injection vulnerabilities.
                    Provide a detailed explanation of any vulnerabilities you find, including the vulnerable code snippet and a suggested fix.
                    If no vulnerabilities are found, respond with "No SQL injection vulnerabilities found."

                    File: {file_path}
                    Code:
                    ```
                    {content}
                    ```
                    """
                    
                    print(f"Analyzing file: {file_path}")
                    response = self.llm.invoke(prompt)
                    if "No SQL injection vulnerabilities found." not in response.content:
                        vulnerabilities.append(response.content)
                    file_count += 1


        # Clean up the cloned repository
        shutil.rmtree(clone_dir)
        
        if not vulnerabilities:
            return f"Successfully cloned {github_url} and finished analysis. No SQL injection vulnerabilities found in the first {file_limit} files."

        return f"Successfully cloned {github_url} and finished analysis. Found the following potential SQL injection vulnerabilities in the first {file_limit} files:\n\n" + "\n\n".join(vulnerabilities)
