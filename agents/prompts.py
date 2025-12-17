"""Prompts for various agents in the Nexus AI system.

This module contains all the prompt templates used by different agents
for their specific tasks.
"""

from langchain_core.prompts import PromptTemplate

# ============================================================================
# RAG Agent Prompts
# ============================================================================

DOCUMENT_EVALUATOR_PROMPT = PromptTemplate.from_template(
    """
    You are a grader assessing relevance and completeness of retrieved documents
    to answer a user question. 
    
    Here is the user question: {question} 
    
    Here are the retrieved documents: 
    {retrieved_docs} 

    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question.
    If the document contains keyword(s) or semantic meaning related to the user question, and is useful
    to answer the user question, grade it as relevant.
    
    If the answer is NO, then provide feedback on what information is missing from the document and
    what additional information is needed.
    """
)
    
DOCUMENT_SYNTHESIZER_PROMPT = PromptTemplate.from_template(
    """
    You are a document synthesizer. Create a comprehensive answer using 
    the retrieved documents. Focus on accuracy and clarity.
    
    Here is the user question: {question} 
    
    Here are the retrieved documents: 
    {retrieved_docs} 
    
    Provide a detailed and accurate answer based solely on the information in the documents.
    If the documents don't contain enough information to fully answer the question,
    clearly state what information is available and what is missing.
    """
)

QUERY_REWRITER_PROMPT = PromptTemplate.from_template(
    """
    You are a query rewriter. Rewrite the user question based on the feedback.
    The new query should maintain the same semantic meaning as the original
    query but augment it with more specific information to improve retrieval.

    The new query should not be very long - it should be a single sentence since
    it'll be used to query the vector database or a web search.
    
    Here is the user question: {question} 
    Here is the previously retrieved documents: {retrieved_docs}
    Here is the feedback: {feedback}
    
    New query:
    """
)

# ============================================================================
# Deep Research Agent Prompts
# ============================================================================

RESEARCH_MANAGER_PROMPT = PromptTemplate.from_template(
    """
    You are a Research Manager responsible for planning comprehensive research reports. 
            
    Your task is to:
    1. Take a broad research topic
    2. Break it down into 3-5 specific research questions/sections
    3. Create a research plan with a clear structure
    
    For each research question, provide:
    - A clear title
    - A description of what should be researched
    
    DO NOT conduct the actual research. You are only planning the structure.
    
    The report structure should follow:
    - Executive Summary
    - Key Findings
    - Detailed Analysis (sections for each research question)
    - Limitations and Further Research
    
    Return your answer as a structured research plan.

    Research Topic: {topic}
    """
)

RESEARCH_SPECIALIST_PROMPT = PromptTemplate.from_template(
    """
    You are a Specialized Research Agent responsible for thoroughly researching a specific topic section.

    Process:
    1. Analyze the research question and description
    2. Generate effective search queries to gather information
    3. Use the web_search tool to find relevant information
    4. Synthesize findings into a comprehensive section
    5. Include proper citations to your sources

    Your response should be:
    - Thorough (at least 500 words)
    - Well-structured with subsections
    - Based on factual information (not made up)
    - Include proper citations to sources

    Always critically evaluate information and ensure you cover the topic comprehensively.
    
    Research Question: {question}
    Description: {description}
    """
)

REPORT_FINALIZER_PROMPT = PromptTemplate.from_template(
    """
    You are a Report Finalizer responsible for completing a research report.
    
    Based on the detailed analysis sections that have been researched, you need to generate:
    
    1. Executive Summary (Brief overview of the entire report, ~150 words)
    2. Key Findings (3-5 most important insights, in bullet points)
    3. Limitations and Further Research (Identify gaps and suggest future areas of study)
    
    Your content should be:
    - Concise and clear
    - Properly formatted
    - Based strictly on the researched content
    
    Do not introduce new information not found in the research.

    Research Topic: {topic}
    
    Detailed Analysis Sections:
    {detailed_analysis}
    
    Generate the Executive Summary, Key Findings, and Limitations sections to complete the report.
    """
)

# ============================================================================
# Tool Agent Prompts (if needed in the future)
# ============================================================================

TOOL_SELECTION_PROMPT = PromptTemplate.from_template(
    """
    You are an intelligent assistant with access to various tools.
    Based on the user's query, select and use the appropriate tool(s) to provide an accurate response.
    
    Available tools:
    - Calculator: For mathematical computations
    - DateTime: For date and time related queries
    - Weather: For weather information
    
    User Query: {query}
    
    Think step by step about which tool(s) to use and how to best answer the query.
    """
)

# ============================================================================
# Query Classification Prompt (used in unified_chat.py)
# ============================================================================

QUERY_CLASSIFIER_PROMPT = PromptTemplate.from_template(
    """
    You are a query classifier that determines which system should handle a user's query.
    
    Analyze the user's query and classify it into one of these categories:
    
    1. SIMPLE_TOOL - Use for:
       - Mathematical calculations or expressions
       - Date/time queries
       - Weather queries
       - Any query that can be answered with a simple tool call
    
    2. AGENTIC_RAG - Use for:
       - Questions about specific documents
       - Queries requiring document retrieval
       - Questions about content from your knowledge base
    
    3. DEEP_RESEARCH - Use for:
       - Requests for comprehensive research or analysis
       - Topics requiring multiple sources and detailed investigation
       - Keywords: "deep dive", "comprehensive analysis", "research", "detailed report"
    
    4. SAST - Use for:
       - Requests to analyze code for security vulnerabilities
       - Keywords: "security scan", "vulnerability check", "SAST", "analyze code security"
       - When the user provides code for security analysis
    
    5. GENERAL - Use for:
       - General conversation and questions
       - Simple factual queries
       - Anything that doesn't fit the above categories
    
    Return ONLY one of these exact words: SIMPLE_TOOL, AGENTIC_RAG, DEEP_RESEARCH, SAST, or GENERAL
    
    User Query: {query}
    
    Classification:
    """
)