"""Unified Chat Implementation combining all agent functionalities.

This implementation combines:
- Tool-using agent (calculator, datetime, weather)
- Agentic RAG for document queries
- Deep research for comprehensive analysis
"""

import os.path as osp
import io
import contextlib
from typing import Dict, List, Optional, Any, Annotated
from enum import Enum

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.prebuilt import create_react_agent
from langgraph.graph import MessagesState
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import PromptTemplate

from core.chat_interface import ChatInterface
from tools.calculator import Calculator
from agents.prompts import QUERY_CLASSIFIER_PROMPT

# Import components from individual agents
from agents.tool_agent import ToolUsingAgentChat
from agents.rag_agent import AgenticRAGChat
from agents.research_agent import DeepResearchChat
from agents.sast_agent import SastAgent
from agents.ssrf_agent import SsrfAgent
from dotenv import load_dotenv
load_dotenv()


class QueryType(Enum):
    """Types of queries the system can handle."""
    SIMPLE_TOOL = "simple_tool"  # Calculator, datetime, weather
    AGENTIC_RAG = "agentic_rag"  # OPM document queries
    DEEP_RESEARCH = "deep_research"  # Comprehensive research
    SAST = "sast"  # Static Application Security Testing (SQL Injection)
    SSRF = "ssrf"  # SSRF Vulnerability Detection
    GENERAL = "general"  # General conversation


class UnifiedChatState(MessagesState):
    """Unified state that uses MessagesState for proper message handling."""
    query_type: Optional[str] = None
    current_agent: Optional[str] = None


class UnifiedChat(ChatInterface):
    """Unified chat implementation that routes queries to appropriate handlers."""
    
    def __init__(self):
        self.router_llm = None
        self.tool_agent = ToolUsingAgentChat()
        self.rag_agent = None
        self.research_agent = None
        self.sast_agent = None
        self.ssrf_agent = None
        self.query_classifier = None
        
    def initialize(self) -> None:
        """Initialize all components for the unified system."""
        print("Initializing Nexus AI Unified System...")
        
        # Initialize router LLM for query classification
        self.router_llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Initialize query classifier
        self._create_query_classifier()
        
        # Initialize all sub-agents
        print("Initializing Tool-Using Agent...")
        self.tool_agent = ToolUsingAgentChat()
        self.tool_agent.initialize()
        
        print("Initializing Agentic RAG...")
        self.rag_agent = AgenticRAGChat()
        self.rag_agent.initialize()
        
        print("Initializing Deep Research Agent...")
        self.research_agent = DeepResearchChat()
        self.research_agent.initialize()
        
        print("Initializing SAST Agent...")
        self.sast_agent = SastAgent()
        self.sast_agent.initialize()

        print("Initializing SSRF Agent...")
        self.ssrf_agent = SsrfAgent()
        self.ssrf_agent.initialize()

        print("Nexus AI System initialized successfully!")
    
    def _create_query_classifier(self):
        """Create the query classifier that routes to appropriate handlers."""
        self.query_classifier = QUERY_CLASSIFIER_PROMPT | self.router_llm
    
    def _classify_query(self, query: str) -> QueryType:
        """Classify the query to determine which handler to use."""
        try:
            result = self.query_classifier.invoke({"query": query})
            classification = result.content.strip().upper()
            
            print(f"Query Classification: {classification}")
            
            # Map to enum
            if classification == "SIMPLE_TOOL":
                return QueryType.SIMPLE_TOOL
            elif classification == "AGENTIC_RAG":
                return QueryType.AGENTIC_RAG
            elif classification == "DEEP_RESEARCH":
                return QueryType.DEEP_RESEARCH
            elif classification == "SAST":
                return QueryType.SAST
            elif classification == "SSRF":
                return QueryType.SSRF
            else:
                return QueryType.GENERAL
                
        except Exception as e:
            print(f"Error in query classification: {e}")
            # Default to general tool agent for safety
            return QueryType.GENERAL
    
    def process_message(self, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Process a message by routing to the appropriate handler.
        
        Uses MessagesState internally for proper state management when needed.
        
        Args:
            message: The user's input message
            chat_history: List of previous chat messages
            
        Returns:
            str: The assistant's response
        """
        print(f"\n{'='*50}")
        print(f"Processing query: {message}")
        print(f"{'='*50}")
        
        # Classify the query
        query_type = self._classify_query(message)
        
        # Create state with messages for tracking
        state = UnifiedChatState(
            messages=[HumanMessage(content=message)],
            query_type=query_type.value,
            current_agent=None
        )
        
        # Route to appropriate handler
        try:
            if query_type == QueryType.SIMPLE_TOOL or query_type == QueryType.GENERAL:
                print("→ Routing to Tool-Using Agent")
                state["current_agent"] = "tool_agent"
                return self.tool_agent.process_message(message, chat_history)
                
            elif query_type == QueryType.AGENTIC_RAG:
                print("→ Routing to Agentic RAG")
                state["current_agent"] = "rag_agent"
                return self.rag_agent.process_message(message, chat_history)
                
            elif query_type == QueryType.DEEP_RESEARCH:
                print("→ Routing to Deep Research Agent")
                state["current_agent"] = "research_agent"
                return self.research_agent.process_message(message, chat_history)
            
            elif query_type == QueryType.SAST:
                print("→ Routing to SAST Agent")
                state["current_agent"] = "sast_agent"
                return self.sast_agent.process_message(message, chat_history)

            elif query_type == QueryType.SSRF:
                print("→ Routing to SSRF Agent")
                state["current_agent"] = "ssrf_agent"
                return self.ssrf_agent.process_message(message, chat_history)

            else:
                # Fallback to tool agent for general queries
                print("→ Routing to Tool-Using Agent (fallback)")
                state["current_agent"] = "tool_agent"
                return self.tool_agent.process_message(message, chat_history)
                
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            print(error_msg)
            # Add error to state messages
            state["messages"].append(AIMessage(content=f"I encountered an error: {str(e)}"))
            return f"I encountered an error while processing your request: {str(e)}. Please try rephrasing your question."