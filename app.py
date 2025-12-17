"""Main application file for Nexus AI Assistant.

This file handles the Gradio interface and orchestrates the chat implementations.
"""


from typing import List, Dict, Tuple
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to Python path so imports work correctly
# root_path = Path(__file__).resolve().parent
# sys.path.append(str(root_path))
# print(f"root path: {root_path}")

import gradio as gr
# Import the unified chat implementation
from agents.unified_chat import UnifiedChat
load_dotenv()

def create_demo():
    """Create the Gradio demo for the unified chat system."""
    
    # Initialize the unified chat implementation
    chat_impl = UnifiedChat()
    
    # Initialize the chat implementation
    try:
        chat_impl.initialize()
        init_status = "✅ All systems ready!"
    except Exception as e:
        init_status = f"❌ Error initializing: {str(e)}"
        print(init_status)
    
    def respond(message: str, history: List[Tuple[str, str]]) -> str:
        """Process a message and return the response.
        
        Args:
            message: The user's input message
            history: List of tuples containing (user_message, assistant_response)
            
        Returns:
            str: The assistant's response
        """
        if not message:
            return "Please enter a message."
        
        # Convert history to the format expected by the chat implementation
        history_dicts = []
        for user_msg, assistant_msg in history:
            history_dicts.append({"role": "user", "content": user_msg})
            history_dicts.append({"role": "assistant", "content": assistant_msg})
        
        try:
            # Process the message
            response = chat_impl.process_message(message, history_dicts)
            return response
        except Exception as e:
            return f"Error processing message: {str(e)}"
    
    
    # Create the Gradio interface using ChatInterface
    demo = gr.ChatInterface(
        fn=respond,
        title="🤖 Nexus AI - Unified Intelligent Assistant",
        description=f"""
        {init_status}
        
        I combine multiple AI capabilities:
        • 🧮 **Calculator & Math** - Complex calculations
        • 📅 **Date & Time** - Current date, time calculations  
        • 🌤️ **Weather** - Real-time weather information
        • 📚 **Document Analysis** - RAG-powered document search
        • 🔬 **Deep Research** - Comprehensive multi-source analysis
        • 🛡️ **SAST (Security Analysis)** - Static Application Security Testing
        • 💬 **General Chat** - Conversational AI
        
        The system automatically routes your query to the most appropriate handler.
        """,
        examples=[
            "What is 847 * 293?",
            "What's today's date?",
            "Perform a SAST analysis on this code: `def sensitive_function(password): print(password)`",
            # "What's the weather in San Francisco?",
            # "Explain quantum computing in simple terms",
            # "Research the impact of AI on healthcare",
            # "Find the SQL injection vulnerabilities in this github repo: `https://github.com/WebGoat/WebGoat`",
        ],
        theme=gr.themes.Soft(),
        analytics_enabled=False,
    )
    
    return demo


if __name__ == "__main__":
    # Create and launch the demo
    demo = create_demo()
    demo.launch()