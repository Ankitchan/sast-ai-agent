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

class SsrfAgent(ChatInterface):
    """SSRF Agent for detecting Server-Side Request Forgery vulnerabilities."""

    def __init__(self):
        self.llm = None
        self.current_repo_path = None
        self.tools = []
        self.agent_executor = None

    def initialize(self) -> None:
        """Initialize components for the SSRF agent."""
        print("SSRF Agent initialized.")
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
        """Process a message and perform SSRF analysis on a GitHub repository.

        Args:
            message: The message containing the GitHub repository URL.
            chat_history: Optional chat history.

        Returns:
            str: A response indicating the result of the SSRF analysis.
        """
        print(f"Received message for SSRF analysis: {message}")

        # Extract GitHub URL from the message
        github_url_match = re.search(r"https://github\.com/[a-zA-Z0-9\-_]+/[a-zA-Z0-9\-_]+", message)
        if not github_url_match:
            return "Please provide a valid GitHub repository URL in the format: https://github.com/username/repository"

        github_url = github_url_match.group(0)
        repo_name = github_url.split("/")[-1]
        clone_dir = os.path.join("/tmp", f"ssrf_{repo_name}")

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
        instructions = """You are a security expert agent designed to analyze code repositories for SSRF (Server-Side Request Forgery) vulnerabilities.

**Repository Location**: """ + clone_dir + """

### Your Task
Perform a comprehensive analysis of the repository to identify SSRF vulnerabilities.

### Analysis Process

1. **Explore the Repository Structure**
   - Use `show_directory_structure` to get an overview of the repository
   - Use `list_directories` and `list_files` to navigate through the codebase
   - Identify files that are likely to make HTTP requests or handle URLs

2. **Identify SSRF-Prone Patterns**
   Look for files that contain:
   - HTTP request libraries (requests, urllib, httpx, axios, fetch, curl, etc.)
   - URL construction or manipulation
   - User-controlled input used in URLs
   - File fetching operations (file_get_contents, wget, etc.)
   - Webhook or callback URL handlers
   - Image/file download functionality
   - API proxy or forwarding functionality
   - URL validation/parsing functions

3. **Analyze Each Relevant File**
   - Use `view_file` to read the complete file contents
   - For large files, use `view_file_lines` to examine specific sections
   - Look for SSRF vulnerabilities:
     * User input directly used in URL without validation
     * Missing or insufficient URL whitelist/blacklist
     * No checks for internal/private IP addresses (127.0.0.1, 192.168.x.x, 10.x.x.x, localhost)
     * URL redirect following without validation
     * DNS rebinding vulnerabilities
     * Protocol smuggling (file://, gopher://, etc.)
     * Missing hostname/domain validation

4. **Document All Findings**
   - Record EVERY file that makes HTTP requests or handles URLs
   - For vulnerable files, note the exact line numbers and vulnerability details
   - Provide code snippets showing the vulnerable code
   - Identify the attack vector and potential impact

5. **Be Thorough**
   - Check common locations: API routes, controllers, views, services, utilities
   - Don't stop after finding one vulnerability - scan the entire repository
   - Review at least the most common file types: .py, .java, .js, .ts, .php, .rb, .go

### SSRF Vulnerability Examples

**Python:**
```python
# VULNERABLE: User input directly in URL
url = request.args.get('url')
response = requests.get(url)

# VULNERABLE: No IP validation
target = user_input
requests.get(f"http://{{{{target}}}}/api/data")
```

**JavaScript/Node.js:**
```javascript
// VULNERABLE: User-controlled URL
const url = req.query.url;
fetch(url).then(res => res.json())

// VULNERABLE: No validation
axios.get(userProvidedUrl)
```

### Output Format

Your final answer MUST be in this exact JSON format:

```json
{{
    "repository": \"""" + clone_dir + """\",
    "http_request_files": [
        "path/to/file1.py",
        "path/to/file2.js"
    ],
    "vulnerable_files": [
        {{
            "file": "path/to/vulnerable_file.py",
            "line": 42,
            "vulnerability_type": "SSRF",
            "severity": "HIGH",
            "description": "User-controlled URL without validation allows SSRF",
            "code_snippet": "url = request.args.get('url')\\nresponse = requests.get(url)",
            "attack_vector": "Attacker can access internal services at 127.0.0.1 or cloud metadata endpoints",
            "recommendation": "Validate URLs against whitelist, block private IP ranges, use URL parser"
        }}
    ],
    "total_files_analyzed": 10,
    "total_http_files": 5,
    "total_vulnerabilities": 2,
    "summary": "Brief summary of findings including critical SSRF risks"
}}
```

**IMPORTANT**:
- Be systematic and thorough
- Use the tools to explore the repository
- Don't make assumptions - actually view the files
- Look for both obvious and subtle SSRF vulnerabilities
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

            print(f"Starting SSRF analysis of repository: {clone_dir}")
            print("This may take several minutes for large repositories...")

            # Invoke the agent once for the entire repository
            response = agent_executor.invoke({
                "input": "Analyze this repository for SSRF vulnerabilities. Start by exploring the structure, then systematically check files for HTTP requests and SSRF risks."
            })

            print("Analysis complete!")

            # Parse the response
            output = response.get("output", "")
            parsed_result = self._parse_json_response(output)

            # Format the response for the user
            if "error" in parsed_result:
                # JSON parsing failed, return raw output
                return f"Analysis completed for {github_url}.\n\n{output}"

            # Successfully parsed JSON
            return self._format_analysis_report(github_url, parsed_result)

        except Exception as e:
            error_msg = f"Error during SSRF analysis: {str(e)}"
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
        report = "# SSRF Vulnerability Analysis Report\n\n"
        report += f"**Repository**: {github_url}\n\n"

        # Summary statistics
        total_vulnerabilities = result.get("total_vulnerabilities", len(result.get("vulnerable_files", [])))
        total_http_files = result.get("total_http_files", len(result.get("http_request_files", [])))
        total_analyzed = result.get("total_files_analyzed", "unknown")

        report += "## Summary\n"
        report += f"- Files Analyzed: {total_analyzed}\n"
        report += f"- Files Making HTTP Requests: {total_http_files}\n"
        report += f"- SSRF Vulnerabilities Found: {total_vulnerabilities}\n\n"

        if result.get("summary"):
            report += f"{result['summary']}\n\n"

        # List HTTP request files
        http_files = result.get("http_request_files", [])
        if http_files:
            report += f"## Files Making HTTP Requests ({len(http_files)})\n"
            for file in http_files:
                report += f"- {file}\n"
            report += "\n"

        # List vulnerabilities
        vulnerable_files = result.get("vulnerable_files", [])
        if vulnerable_files:
            report += f"## SSRF Vulnerabilities Found ({len(vulnerable_files)})\n\n"
            for i, vuln in enumerate(vulnerable_files, 1):
                report += f"### {i}. {vuln.get('file', 'Unknown file')}\n"
                report += f"- **Line**: {vuln.get('line', 'N/A')}\n"
                report += f"- **Severity**: {vuln.get('severity', 'MEDIUM')}\n"
                report += f"- **Type**: {vuln.get('vulnerability_type', 'SSRF')}\n"
                report += f"- **Description**: {vuln.get('description', 'No description provided')}\n"

                if vuln.get('attack_vector'):
                    report += f"- **Attack Vector**: {vuln['attack_vector']}\n"

                if vuln.get('code_snippet'):
                    report += f"- **Vulnerable Code**:\n```\n{vuln['code_snippet']}\n```\n"

                if vuln.get('recommendation'):
                    report += f"- **Recommendation**: {vuln['recommendation']}\n"

                report += "\n"
        else:
            report += "## No SSRF Vulnerabilities Found\n\n"
            report += "No SSRF vulnerabilities were detected in the analyzed files.\n"

        return report
