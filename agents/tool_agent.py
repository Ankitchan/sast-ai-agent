"""Tool-Using Agent implementation.

This implementation focuses on:
- Converting tools to use with LangGraph
- Using the ReAct pattern for autonomous tool selection
- Handling calculator, datetime, and weather queries
"""

from typing import Dict, List, Optional, Any, Annotated
import io
import contextlib
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, AIMessage

from core.chat_interface import ChatInterface
from tools.calculator import Calculator
from dotenv import load_dotenv
load_dotenv()


class ToolUsingAgentChat(ChatInterface):
    """Tool-using agent implementation with calculator, datetime, and weather tools."""
    
    def __init__(self):
        self.llm = None
        self.tools = []
        self.graph = None
    
    def initialize(self) -> None:
        """Initialize components for the tool-using agent.
        
        This sets up:
        - The chat model
        - Tools for calculator, DateTime, and weather
        - The ReAct agent using LangGraph
        """
        # Initialize chat model
        self.llm = init_chat_model("gpt-4o", model_provider="openai")
        
        # Create tools
        self.tools = self._create_tools()
        
        # Create the ReAct agent graph with the tools
        # The agent will autonomously decide which tools to use based on the query
        self.graph = create_react_agent(
            model=self.llm,
            tools=self.tools,
        )
    
    def _create_tools(self) -> List[Any]:
        """Create and return the list of tools for the agent.
        
        Returns:
            List: List of tool objects
        """
        # Calculator tool for mathematical operations
        @tool
        def calculator(expression: Annotated[str, "The mathematical expression to evaluate"]) -> str:
            """Evaluate a mathematical expression using basic arithmetic operations (+, -, *, /, %, //).
            Examples: '5 + 3', '10 * (2 + 3)', '15 / 3', '17 % 5', '20 // 3'
            """
            result = Calculator.evaluate_expression(expression)
            if isinstance(result, str) and result.startswith("Error"):
                raise ValueError(result)
            return str(result)

        # DateTime tool for date/time operations
        @tool
        def execute_datetime_code(code: Annotated[str, "Python code to execute for datetime operations"]) -> str:
            """Execute Python code for datetime operations. The code should use datetime or time modules.
            Examples: 
            - 'print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))'
            - 'print(datetime.datetime.now().strftime("%A, %B %d, %Y"))'
            - 'print(datetime.datetime.now().year)'
            - 'print((datetime.datetime(2025, 12, 25) - datetime.datetime.now()).days)'
            """
            output_buffer = io.StringIO()
            code = f"import datetime\nimport time\n{code}"
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code)
                return output_buffer.getvalue().strip()
            except Exception as e:
                raise ValueError(f"Error executing datetime code: {str(e)}")

        # Weather tool using Tavily search
        @tool
        def get_weather(location: Annotated[str, "The location to get weather for (city, country)"]) -> str:
            """Get the current weather for a given location using web search.
            Examples: 'New York, USA', 'London, UK', 'Tokyo, Japan', 'Paris, France'
            """
            search = TavilySearchResults(max_results=3)
            query = f"current weather temperature conditions {location} today"
            results = search.invoke(query)
            
            if not results:
                return f"Could not find weather information for {location}"
            
            # Combine results for better coverage
            weather_info = []
            for result in results[:2]:  # Use top 2 results
                content = result.get("content", "")
                if content:
                    weather_info.append(content)
            
            if weather_info:
                return " ".join(weather_info)
            else:
                return f"Could not find detailed weather information for {location}"
        
        return [calculator, execute_datetime_code, get_weather]

    def _convert_history_to_messages(self, chat_history: Optional[List[Dict[str, str]]]) -> List:
        """Convert chat history to LangChain message format.
        
        Args:
            chat_history: List of dicts with 'role' and 'content' keys
            
        Returns:
            List of LangChain message objects
        """
        messages = []
        if chat_history:
            for msg in chat_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        return messages

    def process_message(self, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Process a message using the tool-using agent.
        
        The ReAct agent will:
        1. Consider the full conversation history
        2. Analyze the query in context
        3. Decide which tool(s) to use
        4. Execute the tool(s)
        5. Formulate a response
        
        Args:
            message: The user's input message
            chat_history: List of previous chat messages
            
        Returns:
            str: The assistant's response
        """
        try:
            # Convert chat history to messages
            history_messages = self._convert_history_to_messages(chat_history)
            
            # Add the current message
            history_messages.append(HumanMessage(content=message))
            
            # Run the graph with the full conversation history
            result = self.graph.invoke({"messages": history_messages})
            
            # Run the graph with the user's message
            # result = self.graph.invoke({"messages": [("user", message)]})
            
            # Extract the final response
            if result.get("messages"):
                final_message = result["messages"][-1]
                # Handle different message formats
                if hasattr(final_message, 'content'):
                    return final_message.content
                else:
                    return str(final_message)
            else:
                return "I couldn't process that request. Please try rephrasing."
                
        except Exception as e:
            print(f"Error in tool agent: {e}")
            return f"I encountered an error while processing your request: {str(e)}. Please try again."