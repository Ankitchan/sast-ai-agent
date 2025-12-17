"""Factory for creating agent implementations.

This module contains factory methods for creating the appropriate chat implementation
based on the selected agent mode.
"""

from enum import Enum
from nexus_ai.core.chat_interface import ChatInterface
from nexus_ai.agents.research_agent import DeepResearchChat
from nexus_ai.agents.rag_agent import AgenticRAGChat
from nexus_ai.agents.tool_agent import ToolUsingAgentChat
from nexus_ai.agents.unified_chat import UnifiedChat


class AgentMode(Enum):
    """Enum for different agent implementation modes."""
    TOOL_AGENT = "tool"
    RAG_AGENT = "rag"
    RESEARCH_AGENT = "research"
    UNIFIED = "unified"  # Default unified mode


def create_chat_implementation(mode: AgentMode = AgentMode.UNIFIED) -> ChatInterface:
    """Create a chat implementation for the specified agent mode.
    
    Args:
        mode: Which agent implementation to use (defaults to UNIFIED)
        
    Returns:
        ChatInterface: The initialized chat implementation
    """
    if mode == AgentMode.TOOL_AGENT:
        return ToolUsingAgentChat()
    elif mode == AgentMode.RAG_AGENT:
        return AgenticRAGChat()
    elif mode == AgentMode.RESEARCH_AGENT:
        return DeepResearchChat()
    else:
        # Default to unified mode
        return UnifiedChat()