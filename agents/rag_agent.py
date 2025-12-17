"""Agentic RAG implementation.

This implementation focuses on:
- Building an Agentic RAG system with dynamic search strategy
- Using LangGraph for controlling the RAG workflow
- Evaluating retrieved information quality
"""

import os.path as osp
from typing import Dict, List, Optional, Any
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END, START, MessagesState
from langgraph.graph.message import add_messages

# For document retrieval
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langchain_core.tools.retriever import create_retriever_tool
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.chat_interface import ChatInterface
from agents.prompts import (
    DOCUMENT_EVALUATOR_PROMPT,
    DOCUMENT_SYNTHESIZER_PROMPT,
    QUERY_REWRITER_PROMPT,
)
from langchain_core.prompts import PromptTemplate
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
load_dotenv()

# NOTE: Update this to the path of your documents
# For Hugging Face Spaces, use: "/home/user/app/documents/"
# For local development, use your local path
BASE_DIR = "data/"

# Add your document files here
FILE_PATHS = [
    # Example for OPM documents (you can replace with your own documents):
    osp.join(BASE_DIR, "2019-annual-performance-report.pdf"),
    osp.join(BASE_DIR, "2020-annual-performance-report.pdf"),
    osp.join(BASE_DIR, "2021-annual-performance-report.pdf"),
    osp.join(BASE_DIR, "2022-annual-performance-report.pdf"),
    

]


class DocumentEvaluation(BaseModel):
    """Evaluation result for retrieved documents."""
    is_sufficient: bool = Field(description="Whether the documents provide sufficient information")
    feedback: str = Field(description="Feedback about the document quality and what's missing")


class AgenticRAGState(MessagesState):
    """State for the Agentic RAG workflow using MessagesState as base."""
    # MessagesState already handles messages with add_messages reducer
    feedback: str = ""
    is_sufficient: bool = False
    retry_count: int = 0  # Track number of retries to prevent infinite loops
    max_retries: int = 3  # Maximum number of query rewrites allowed
    current_query_index: int = 0  # Track which message is the current query


class AgenticRAGChat(ChatInterface):
    """Agentic RAG implementation with dynamic retrieval and evaluation."""
    
    def __init__(self):
        self.llm = None
        self.embeddings = None
        self.evaluator_llm = None
        self.vector_store = None
        self.tools = []
        self.graph = None
    
    def initialize(self) -> None:
        """Initialize components for the Agentic RAG system."""
        # Initialize models
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.evaluator_llm = self.llm.with_structured_output(DocumentEvaluation)

        # Check if documents are configured
        if FILE_PATHS and all(osp.exists(f) for f in FILE_PATHS):
            # Load documents and create vector store
            docs = self._load_and_process_documents()
            print(f"Loading {len(docs)} documents into vector store")
            self.vector_store = InMemoryVectorStore(embedding=self.embeddings)
            self.vector_store.add_documents(docs)
        else:
            print("Warning: No documents configured for RAG. Add document paths to FILE_PATHS.")
            # Create empty vector store
            self.vector_store = InMemoryVectorStore(embedding=self.embeddings)
        
        # Create tools
        self.tools = self._create_tools()
        
        # Create the graph
        self.graph = self._create_graph()

    def _load_and_process_documents(self) -> List[Document]:
        """Load and process documents for RAG."""
        docs = []
        for file_path in FILE_PATHS:
            if not osp.exists(file_path):
                print(f"Warning: File not found - {file_path}")
                continue
                
            print(f"Loading document from {file_path}")
            try:
                loader = PyPDFLoader(file_path)
                page_docs = loader.load()
                
                # Combine all pages and split into chunks
                combined_doc = "\n".join([doc.page_content for doc in page_docs])
                
                # Use RecursiveCharacterTextSplitter for better chunking
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000, 
                    chunk_overlap=200,
                    separators=["\n\n", "\n", ".", " ", ""]
                )
                chunks = text_splitter.split_text(combined_doc)
                
                # Convert chunks to Document objects with metadata
                docs.extend([
                    Document(
                        page_content=chunk, 
                        metadata={"source": osp.basename(file_path)}
                    ) for chunk in chunks
                ])
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                
        return docs
    
    def _create_tools(self) -> List[Any]:
        """Create retriever and search tools."""
        tools = []
        
        # Create retriever tool if we have documents
        if self.vector_store:
            retriever = self.vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 3}
            )
            retriever_tool = create_retriever_tool(
                retriever,
                name="search_documents",
                description=(
                    "Search through the document database. "
                    "Use this for questions about content in the loaded documents."
                )
            )
            tools.append(retriever_tool)
        
        # Create web search tool
        @tool("web_search")
        def search_web(query: str) -> list[dict]:
            """
            Search the web for the latest information on any topic.
            
            Args:
                query: The search query to look up
                
            Returns:
                List of search results with title, content, and URL
            """
            search = TavilySearchResults(max_results=3)
            return search.invoke(query)
        
        tools.append(search_web)
        
        return tools

    def _generate_query_or_respond(self, state: AgenticRAGState):
        """Generate a query or respond based on the current state."""
        print("Generating query or responding...")
        
        prompt = PromptTemplate.from_template(
            """
            You are a helpful assistant that can answer questions using the provided tools.
            
            Available tools:
            - search_documents: Search through loaded documents
            - web_search: Search the web for information
            
            Based on the user's query, decide whether to use tools or respond directly.
            Use tools when you need specific information to answer the question accurately.

            Query: {question}
            """
        )
        
        # Get the latest message (either original or rewritten query)
        question = state["messages"][-1].content
        chain = prompt | self.llm.bind_tools(self.tools)
        
        response = chain.invoke({"question": question})
        return {"messages": [response]}

    def _evaluate_documents(self, state: AgenticRAGState):
        """Evaluate the documents retrieved from the retriever tool."""
        print("Evaluating documents...")
        
        # Check if we've hit max retries
        if state.get("retry_count", 0) >= state.get("max_retries", 3):
            print(f"Max retries ({state.get('max_retries', 3)}) reached. Forcing synthesis with available documents.")
            return {
                "is_sufficient": True,  # Force synthesis even if not perfect
                "feedback": "Maximum retries reached. Using available documents."
            }
        
        # Get the CURRENT user question, not the first message in history
        # Use the current_query_index to get the right message
        current_query_index = state.get("current_query_index", 0)
        
        # Find the current query message
        user_messages = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
        if current_query_index < len(state["messages"]):
            user_question = state["messages"][current_query_index].content
        else:
            # Fallback: get the last user message
            user_question = user_messages[-1].content if user_messages else state["messages"][-1].content
        
        # Get the retrieved documents (should be the last message)
        retrieved_docs = state["messages"][-1].content
        
        print(f"Evaluating for query: '{user_question[:50]}...'")  # Debug print
        
        chain = DOCUMENT_EVALUATOR_PROMPT | self.evaluator_llm
        evaluation = chain.invoke({
            "question": user_question, 
            "retrieved_docs": retrieved_docs
        })
        
        print(f"Evaluation result: {evaluation} (Retry {state.get('retry_count', 0)}/{state.get('max_retries', 3)})")
        return {
            "is_sufficient": evaluation.is_sufficient,
            "feedback": evaluation.feedback
        }

    def _synthesize_answer(self, state: AgenticRAGState):
        """Synthesize the final answer from retrieved documents."""
        print("Synthesizing answer...")
        
        # Get the CURRENT user question using the index
        current_query_index = state.get("current_query_index", 0)
        
        # Find the current query message
        user_messages = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
        if current_query_index < len(state["messages"]):
            user_question = state["messages"][current_query_index].content
        else:
            # Fallback: get the last user message
            user_question = user_messages[-1].content if user_messages else state["messages"][-1].content
        
        # Get the retrieved documents
        retrieved_docs = state["messages"][-1].content
        
        print(f"Synthesizing answer for: '{user_question[:50]}...'")  # Debug print
        
        chain = DOCUMENT_SYNTHESIZER_PROMPT | self.llm
        answer = chain.invoke({
            "question": user_question, 
            "retrieved_docs": retrieved_docs
        })
        
        return {"messages": [answer]}

    def _query_rewriter(self, state: AgenticRAGState):
        """Rewrite the query based on evaluation feedback."""
        print("Rewriting query...")
        
        # Increment retry count
        current_retry = state.get("retry_count", 0)
        
        # Get the CURRENT user question using the index
        current_query_index = state.get("current_query_index", 0)
        
        # Find the current query message
        user_messages = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
        if current_query_index < len(state["messages"]):
            user_question = state["messages"][current_query_index].content
        else:
            # Fallback: get the last user message
            user_question = user_messages[-1].content if user_messages else state["messages"][-1].content
        
        retrieved_docs = state["messages"][-1].content
        feedback = state["feedback"]
        
        print(f"Rewriting query for: '{user_question[:50]}...'")  # Debug print
        
        chain = QUERY_REWRITER_PROMPT | self.llm
        new_query = chain.invoke({
            "question": user_question, 
            "feedback": feedback,
            "retrieved_docs": retrieved_docs
        })
        
        print(f"Rewritten query (Attempt {current_retry + 1}/{state.get('max_retries', 3)}): {new_query.content}")
        return {
            "messages": [new_query],
            "retry_count": current_retry + 1  # Increment retry count
        }
    
    def _create_graph(self) -> Any:
        """Create the agentic RAG graph."""
        # Create the graph builder
        graph_builder = StateGraph(AgenticRAGState)
        
        # Add nodes
        graph_builder.add_node("generate_query_or_respond", self._generate_query_or_respond)
        graph_builder.add_node("retrieve_documents", ToolNode(self.tools))
        graph_builder.add_node("evaluate_documents", self._evaluate_documents)
        graph_builder.add_node("synthesize_answer", self._synthesize_answer)
        graph_builder.add_node("query_rewriter", self._query_rewriter)

        # Add edges
        graph_builder.add_edge(START, "generate_query_or_respond")
        
        # Conditional edge: if tools were called, retrieve documents; else end
        graph_builder.add_conditional_edges(
            "generate_query_or_respond",
            tools_condition,
            {
                "tools": "retrieve_documents",
                END: END,
            },
        )
        
        # After retrieval, evaluate documents
        graph_builder.add_edge("retrieve_documents", "evaluate_documents")
        
        # Conditional edge: if sufficient, synthesize; else rewrite query
        graph_builder.add_conditional_edges(
            "evaluate_documents",
            lambda x: "synthesize_answer" if x["is_sufficient"] else "query_rewriter",
            {
                "synthesize_answer": "synthesize_answer",
                "query_rewriter": "query_rewriter",
            },
        )
        
        # After rewriting, generate new query
        graph_builder.add_edge("query_rewriter", "generate_query_or_respond")
        
        # After synthesizing, end
        graph_builder.add_edge("synthesize_answer", END)
        
        return graph_builder.compile()
    
    
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
        """Process a message using the Agentic RAG system."""
        print("\n=== STARTING AGENTIC RAG QUERY ===")
        print(f"Query: {message}")
        
        # Convert chat history to messages
        history_messages = self._convert_history_to_messages(chat_history)
    
        # Mark the position where the current query starts
        # This is important for the evaluator to know which is the actual query
        history_length = len(history_messages)
        
        # Add the current message
        current_query_message = HumanMessage(content=message)
        history_messages.append(current_query_message)
        
        # Create initial state with full conversation history
        # Store the index of the current query for reference
        state = AgenticRAGState(
            messages=history_messages,
            feedback="",
            is_sufficient=False,
            retry_count=0,
            max_retries=3,
            # Add this to track the current query index
            current_query_index=history_length  # This is the index of the current query
        )
        
        try:
            # Run the workflow with increased recursion limit
            config = {"recursion_limit": 30}
            result = self.graph.invoke(state, config=config)
            
            print("\n=== RAG QUERY COMPLETED ===")
            
            # Return the final answer
            if result.get("messages"):
                final_message = result["messages"][-1]
                if hasattr(final_message, 'content'):
                    return final_message.content
                else:
                    return str(final_message)
            else:
                return "I couldn't find relevant information to answer your question."
                
        except Exception as e:
            print(f"Error in RAG processing: {e}")
            if "recursion" in str(e).lower():
                return ("I had difficulty finding the exact information you're looking for in the documents. "
                    "Based on the available documents, I can see references to various topics, "
                    "but I couldn't find specific details. You might want to try asking about a specific aspect.")
            return f"I encountered an error while searching for information: {str(e)}"