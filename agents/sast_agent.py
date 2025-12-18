from typing import List, Dict, Optional, Any
import os
import re
import shutil
import git
import json

from core.chat_interface import ChatInterface
from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate


# Import our custom tools
from tools.view_file_tools import ViewFileTool, ViewFileLinesTool
from tools.view_directory_tools import (
    DirectoryListingTool,
    FileListingTool,
    DirectoryStructureTool,
)

class SastAgent(ChatInterface):
    """SAST Agent for static application security testing."""

    def __init__(self):
        self.llm = None
        self.current_repo_path = None
        self.tools = []
        self.agent_executor = None

    def initialize(self) -> None:
        """Initialize components for the SAST agent."""
        print("SAST Agent initialized.")
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)

        # Initialize tools once
        self.tools = [
            ViewFileTool(),
            ViewFileLinesTool(),
            DirectoryListingTool(),
            FileListingTool(),
            DirectoryStructureTool(),
        ]
    
    def cleanup(self) -> None:
        """Clean up any cloned repositories."""
        if self.current_repo_path and os.path.exists(self.current_repo_path):
            try:
                shutil.rmtree(self.current_repo_path)
                print(f"Cleaned up repository at {self.current_repo_path}")
                self.current_repo_path = None
            except Exception as e:
                print(f"Error cleaning up repository: {e}")

    def _parse_json_response(self, output: str) -> Dict[str, Any]:
        """Extract and parse JSON from agent response.

        Args:
            output: The agent's output string

        Returns:
            Parsed JSON as a dictionary
        """
        try:
            # Try to find JSON block in markdown format
            if "```json" in output:
                json_str = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                # Try generic code block
                json_str = output.split("```")[1].split("```")[0].strip()
            elif "{" in output and "}" in output:
                # Find first { and last }
                start = output.index("{")
                end = output.rindex("}") + 1
                json_str = output[start:end]
            else:
                # No JSON found
                return {"error": "No JSON found in response", "raw_output": output}

            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError, IndexError) as e:
            return {"error": f"JSON parsing error: {str(e)}", "raw_output": output}

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
        github_url_match = re.search(r"https://github\.com/[a-zA-Z0-9\-_]+/[a-zA-Z0-9\-_]+", message)
        if not github_url_match:
            return "Please provide a valid GitHub repository URL in the format: https://github.com/username/repository"

        github_url = github_url_match.group(0)
        repo_name = github_url.split("/")[-1]
        clone_dir = os.path.join("/tmp", f"sast_{repo_name}")

        # Clean up any previous repository
        self.cleanup()

        # Clone the repository
        print(f"Cloning repository: {github_url}")
        try:
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)
            git.Repo.clone_from(github_url, clone_dir)
            self.current_repo_path = clone_dir
            print(f"Repository cloned successfully to: {clone_dir}")
        except Exception as e:
            return f"Error cloning the repository: {e}"

        # Create the prompt template for the ReAct agent
        # Note: The ReAct framework requires these specific variables:
        # {tools}, {tool_names}, {agent_scratchpad}, {input}
        instructions = """You are a security expert agent designed to analyze code repositories for SQL injection vulnerabilities.

**Repository Location**: """ + clone_dir + """

### Your Task
Perform a comprehensive analysis of the repository to identify SQL injection vulnerabilities.

### Analysis Process

1. **Explore the Repository Structure**
   - Use `show_directory_structure` to get an overview of the repository
   - Use `list_directories` and `list_files` to navigate through the codebase
   - Identify files that are likely to contain database interactions (look for common patterns)

2. **Identify SQL Usage Patterns**
   Look for files that contain:
   - Database query execution (`.execute()`, `.raw()`, `cursor.execute()`, etc.)
   - SQL keywords (SELECT, INSERT, UPDATE, DELETE, WHERE, etc.)
   - Database library imports (sqlite3, psycopg2, pymysql, django.db, SQLAlchemy, etc.)
   - ORM usage (Django ORM, SQLAlchemy, etc.)

3. **Analyze Each Relevant File**
   - Use `view_file` to read the complete file contents
   - For large files, use `view_file_lines` to examine specific sections
   - Look for SQL injection vulnerabilities:
     * String concatenation or f-strings used to build SQL queries
     * User input directly embedded in queries without sanitization
     * Lack of parameterized queries or prepared statements
     * Raw SQL execution with untrusted input

4. **Document All Findings**
   - Record EVERY file that uses SQL (even if not vulnerable)
   - For vulnerable files, note the exact line numbers and vulnerability details
   - Provide code snippets showing the vulnerable code

5. **Be Thorough**
   - Check common locations: views, models, controllers, api endpoints, database utilities
   - Don't stop after finding one vulnerability - scan the entire repository
   - Review at least the most common file types: .py, .java, .js, .ts, .php, .rb, .go

### Output Format

Your final answer MUST be in this exact JSON format:

```json
{{
    "repository": \"""" + clone_dir + """\",
    "sql_files": [
        "path/to/file1.py",
        "path/to/file2.py"
    ],
    "vulnerable_files": [
        {{
            "file": "path/to/vulnerable_file.py",
            "line": 42,
            "vulnerability_type": "SQL Injection",
            "severity": "HIGH",
            "description": "User input concatenated directly into SQL query",
            "code_snippet": "query = 'SELECT * FROM users WHERE id=' + user_id",
            "recommendation": "Use parameterized queries instead"
        }}
    ],
    "total_files_analyzed": 10,
    "total_sql_files": 3,
    "total_vulnerabilities": 1,
    "summary": "Brief summary of findings"
}}
```

**IMPORTANT**:
- Be systematic and thorough
- Use the tools to explore the repository
- Don't make assumptions - actually view the files
- Include ALL findings in your final JSON response

TOOLS:
------

You have access to the following tools:

{tools}

To use a tool, please use the following format:

```
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
```

When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:

```
Thought: Do I need to use a tool? No
Final Answer: [your response here]
```

Begin!

Question: {input}
Thought: {agent_scratchpad}"""

        try:
            # Create the prompt with required ReAct variables
            prompt = PromptTemplate.from_template(instructions)

            # Create the agent with tools
            agent = create_react_agent(self.llm, self.tools, prompt)

            # Create executor with higher limits for thorough analysis
            agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=100,  # Allow many iterations for comprehensive analysis
                max_execution_time=600,  # 10 minutes timeout
            )

            print(f"Starting SAST analysis of repository: {clone_dir}")
            print("This may take several minutes for large repositories...")

            # Invoke the agent once for the entire repository
            response = agent_executor.invoke({
                "input": "Analyze this repository for SQL injection vulnerabilities. Start by exploring the structure, then systematically check files for SQL usage and vulnerabilities."
            })

            print("Analysis complete!")
            print(f"DEBUG: Response keys: {response.keys()}")

            # Parse the response
            output = response.get("output", "")
            print(f"DEBUG: Output length: {len(output)} characters")
            print(f"DEBUG: First 200 chars of output: {output[:200]}")

            parsed_result = self._parse_json_response(output)
            print(f"DEBUG: Parsed result keys: {parsed_result.keys()}")

            # Format the response for the user
            if "error" in parsed_result:
                # JSON parsing failed, return raw output
                print("DEBUG: JSON parsing failed, returning raw output")
                return f"Analysis completed for {github_url}.\n\n{output}"

            # Successfully parsed JSON
            print("DEBUG: JSON parsed successfully, formatting report")
            formatted_report = self._format_analysis_report(github_url, parsed_result)
            print(f"DEBUG: Formatted report length: {len(formatted_report)} characters")
            print(f"DEBUG: First 300 chars of report:\n{formatted_report[:300]}")
            return formatted_report

        except Exception as e:
            error_msg = f"Error during SAST analysis: {str(e)}"
            print(error_msg)
            return error_msg
        finally:
            # Keep repository for potential follow-up questions
            # User can manually clean up or it will be cleaned on next analysis
            print(f"Repository kept at: {clone_dir} (will be cleaned up on next analysis)")

    def _format_analysis_report(self, github_url: str, result: Dict[str, Any]) -> str:
        """Format the analysis results into a readable report.

        Args:
            github_url: The URL of the analyzed repository
            result: Parsed JSON results from the agent

        Returns:
            Formatted report string
        """
        report = "# SAST Analysis Report\n\n"
        report += f"**Repository**: {github_url}\n\n"

        # Summary statistics
        total_vulnerabilities = result.get("total_vulnerabilities", len(result.get("vulnerable_files", [])))
        total_sql_files = result.get("total_sql_files", len(result.get("sql_files", [])))
        total_analyzed = result.get("total_files_analyzed", "unknown")

        report += "## Summary\n"
        report += f"- Files Analyzed: {total_analyzed}\n"
        report += f"- Files Using SQL: {total_sql_files}\n"
        report += f"- Vulnerabilities Found: {total_vulnerabilities}\n\n"

        if result.get("summary"):
            report += f"{result['summary']}\n\n"

        # List SQL files
        sql_files = result.get("sql_files", [])
        if sql_files:
            report += f"## Files Using SQL ({len(sql_files)})\n"
            for file in sql_files:
                report += f"- {file}\n"
            report += "\n"

        # List vulnerabilities
        vulnerable_files = result.get("vulnerable_files", [])
        if vulnerable_files:
            report += f"## Vulnerabilities Found ({len(vulnerable_files)})\n\n"
            for i, vuln in enumerate(vulnerable_files, 1):
                report += f"### {i}. {vuln.get('file', 'Unknown file')}\n"
                report += f"- **Line**: {vuln.get('line', 'N/A')}\n"
                report += f"- **Severity**: {vuln.get('severity', 'MEDIUM')}\n"
                report += f"- **Type**: {vuln.get('vulnerability_type', 'SQL Injection')}\n"
                report += f"- **Description**: {vuln.get('description', 'No description provided')}\n"

                if vuln.get('code_snippet'):
                    report += f"- **Vulnerable Code**:\n```\n{vuln['code_snippet']}\n```\n"

                if vuln.get('recommendation'):
                    report += f"- **Recommendation**: {vuln['recommendation']}\n"

                report += "\n"
        else:
            report += "## No Vulnerabilities Found\n\n"
            report += "No SQL injection vulnerabilities were detected in the analyzed files.\n"

        return report
