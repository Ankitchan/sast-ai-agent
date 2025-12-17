"""Deep Research Multi-Agent System implementation.

This implementation focuses on:
- Building a multi-agent system for comprehensive research
- Using LangGraph with MessagesState for proper state management
- Synthesizing research findings into structured reports
"""

from typing import Dict, List, Optional, Any, Annotated
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START, MessagesState
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from core.chat_interface import ChatInterface
from opik.integrations.langchain import OpikTracer
from agents.prompts import (
    RESEARCH_MANAGER_PROMPT,
    REPORT_FINALIZER_PROMPT,
)
from dotenv import load_dotenv
load_dotenv()


class ResearchQuestion(BaseModel):
    """A research question with a title and description."""
    title: str = Field(description="The title of the research question/section")
    description: str = Field(description="Description of what to research for this section")
    completed: bool = Field(default=False, description="Whether research has been completed for this section")


class ResearchPlan(BaseModel):
    """The overall research plan created by the Research Manager."""
    topic: str = Field(description="The main research topic")
    questions: List[ResearchQuestion] = Field(description="The list of research questions to investigate")
    current_question_index: int = Field(default=0, description="Index of the current question being researched")


class Report(BaseModel):
    """The final research report structure."""
    executive_summary: Optional[str] = Field(default=None, description="Executive summary of the research")
    key_findings: Optional[str] = Field(default=None, description="Key findings from the research")
    detailed_analysis: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed analysis sections")
    limitations: Optional[str] = Field(default=None, description="Limitations and further research")


class ResearchState(MessagesState):
    """State tracking for the deep research workflow using MessagesState as base."""
    research_plan: Optional[ResearchPlan] = None
    report: Optional[Report] = None
    next_step: str = "research_manager"
    
    # MessagesState already handles messages with add_messages reducer


class DeepResearchChat(ChatInterface):
    """Deep research implementation using multi-agent system with proper state management."""
    
    def __init__(self):
        self.llm = None
        self.research_manager = None
        self.specialized_research_agent = None
        self.finalizer = None
        self.workflow = None
        self.tavily_search_tool = None
    
    def initialize(self) -> None:
        """Initialize components for the deep research system."""
        # Initialize LLM model
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Create Tavily search tool for agents
        self.tavily_search_tool = TavilySearchResults(max_results=5)
        
        # Create components
        self.research_manager = self._create_research_manager()
        self.specialized_research_agent = self._create_specialized_research_agent()
        self.finalizer = self._create_finalizer()
        
        # Create the workflow graph using these agents
        self.workflow = self._create_workflow()
        
        # Optional: Create Opik Tracer for monitoring
        try:
            self.tracer = OpikTracer(
                graph=self.workflow.get_graph(xray=True),
                project_name="nexus-research-workflow"
            )
        except:
            self.tracer = None
            print("Opik tracer not available, continuing without monitoring")
    
    def _create_research_manager(self) -> Any:
        """Create the research manager agent."""
        research_manager = (
            RESEARCH_MANAGER_PROMPT 
            | self.llm.with_structured_output(ResearchPlan)
        )
        
        return research_manager

    def _create_specialized_research_agent(self) -> Any:
        """Create specialized research agents."""
        # Create search tool for the agent
        @tool("web_search")
        def search_web(query: str) -> str:
            """Search the web for information on the research topic."""
            results = self.tavily_search_tool.invoke(query)
            formatted_results = []
            
            for i, result in enumerate(results, 1):
                formatted_results.append(f"Result {i}:")
                formatted_results.append(f"Title: {result.get('title', 'N/A')}")
                formatted_results.append(f"Content: {result.get('content', 'N/A')}")
                formatted_results.append(f"URL: {result.get('url', 'N/A')}")
                formatted_results.append("")
            
            return "\n".join(formatted_results)
        
        # Create the specialized agent
        tools = [search_web]
        
        # Define the system message for the specialized research agent
        system_message = """You are a Specialized Research Agent responsible for thoroughly researching a specific topic section.

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
        """
        
        # Create the specialized research agent
        specialized_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            prompt=system_message
        )
        
        return specialized_agent
    
    def _create_finalizer(self) -> Any:
        """Create the finalizer component."""
        finalizer = REPORT_FINALIZER_PROMPT | self.llm | StrOutputParser()
        return finalizer
    
    def _create_workflow(self) -> Any:
        """Create the multi-agent deep research workflow with proper MessagesState usage."""
        # Create a state graph
        workflow = StateGraph(ResearchState)
        
        # Define the nodes
        
        # Research Manager Node
        def research_manager_node(state: ResearchState) -> Dict:
            """Create the research plan and update messages."""
            print("\n=== RESEARCH MANAGER NODE ===")
            
            # Get the topic from the LAST user message (not first)
            # This handles conversation context better
            user_messages = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
            topic = user_messages[-1].content if user_messages else state["messages"][-1].content
            
            print(f"Planning research for topic: {topic}")
            
            # Generate research plan
            research_plan = self.research_manager.invoke({"topic": topic})
            print(f"Created research plan with {len(research_plan.questions)} questions")
            
            # Initialize empty report structure
            report = Report(
                detailed_analysis=[
                    {"title": q.title, "content": None, "sources": []} 
                    for q in research_plan.questions
                ]
            )
    
            # Add planning message to state
            planning_msg = AIMessage(
                content=f"Research plan created with {len(research_plan.questions)} sections to investigate."
            )
            
            return {
                "messages": [planning_msg],
                "research_plan": research_plan,
                "report": report,
            }
        
        # Specialized Research Node
        def specialized_research_node(state: ResearchState) -> Dict:
            """Conduct research on the current question and update messages."""
            print("\n=== SPECIALIZED RESEARCH NODE ===")
            
            research_plan = state["research_plan"]
            assert research_plan is not None, "Research plan is None"
            current_index = research_plan.current_question_index
            
            if current_index >= len(research_plan.questions):
                print("All research questions completed")
                return {}
            
            current_question = research_plan.questions[current_index]
            print(f"Researching question {current_index + 1}/{len(research_plan.questions)}: "
                  f"{current_question.title}")
            
            # Create input for the specialized agent
            research_input = {
                "messages": [
                    ("user", f"""Research the following topic thoroughly:
                    
                    Topic: {current_question.title}
                    
                    Description: {current_question.description}
                    
                    Provide a detailed analysis with proper citations to sources.
                    """)
                ]
            }
            
            # Invoke the specialized agent
            result = self.specialized_research_agent.invoke(research_input)
            
            # Extract content from the result
            last_message = result["messages"][-1]
            if isinstance(last_message, tuple):
                content = last_message[1]
            else:
                content = last_message.content
            
            # Parse out sources from the content
            sources = []
            for line in content.split("\n"):
                if "http" in line and "://" in line:
                    sources.append(line.strip())
            
            # Update the research plan
            research_plan.questions[current_index].completed = True
            
            # Update the report
            report = state["report"]
            assert report is not None, "Report is None"
            report.detailed_analysis[current_index]["content"] = content
            report.detailed_analysis[current_index]["sources"] = sources
            
            # Move to the next question
            research_plan.current_question_index += 1
            
            # Add research progress message
            progress_msg = AIMessage(
                content=f"Completed research for section: {current_question.title}"
            )
            
            return {
                "messages": [progress_msg],
                "research_plan": research_plan,
                "report": report,
            }
            
        # Research Evaluator Node
        def evaluator_node(state: ResearchState) -> Dict:
            """Evaluate the research progress and determine next steps."""
            print("\n=== EVALUATOR NODE ===")
            
            research_plan = state["research_plan"]
            assert research_plan is not None, "Research plan is None"
            
            # Check if we've completed all questions
            all_completed = research_plan.current_question_index >= len(research_plan.questions)
            
            if all_completed:
                print("All research questions have been addressed. Moving to finalizer.")
                eval_msg = AIMessage(content="All research sections completed. Finalizing report...")
                return {
                    "messages": [eval_msg],
                    "next_step": "finalize"
                }
            else:
                # We have more sections to research
                next_section = research_plan.questions[research_plan.current_question_index].title
                print(f"More research needed. Moving to next section: {next_section}")
                eval_msg = AIMessage(content=f"Moving to research section: {next_section}")
                return {
                    "messages": [eval_msg],
                    "next_step": "research"
                }
        
        # Finalizer Node
        def finalizer_node(state: ResearchState) -> Dict:
            """Finalize the research report and update messages."""
            print("\n=== FINALIZER NODE ===")
            
            research_plan = state["research_plan"]
            report = state["report"]
            assert report is not None, "Report is None"
            assert research_plan is not None, "Research plan is None"
            
            # Prepare the detailed analysis for the finalizer
            detailed_analysis = "\n\n".join([
                f"## {section['title']}\n{section['content']}"
                for section in report.detailed_analysis
                if section['content'] is not None
            ])
            
            # Generate the final sections
            final_sections = self.finalizer.invoke({
                "topic": research_plan.topic,
                "detailed_analysis": detailed_analysis
            })
            
            # Parse the final sections
            sections = final_sections.split("\n\n")
            
            # Update the report
            if len(sections) >= 3:
                report.executive_summary = sections[0].replace("# Executive Summary", "").strip()
                report.key_findings = sections[1].replace("# Key Findings", "").strip()
                report.limitations = sections[2].replace("# Limitations and Further Research", "").strip()
            
            # Format the final report
            report_message = self._format_report(report)
            
            return {
                "messages": [report_message],
            }
        
        # Add nodes to the graph
        workflow.add_node("research_manager", research_manager_node)
        workflow.add_node("specialized_research", specialized_research_node)
        workflow.add_node("evaluate", evaluator_node)
        workflow.add_node("finalizer", finalizer_node)
        
        # Add edges
        workflow.add_edge(START, "research_manager")
        workflow.add_edge("research_manager", "specialized_research")
        workflow.add_edge("specialized_research", "evaluate")
        
        # Add conditional edges from evaluator
        workflow.add_conditional_edges(
            "evaluate",
            lambda x: x["next_step"],
            {
                "research": "specialized_research",
                "finalize": "finalizer"
            }
        )
        workflow.add_edge("finalizer", END)
        
        # Compile the workflow
        return workflow.compile()
    
    def _format_report(self, report: Report) -> AIMessage:
        """Format the research report for presentation."""
        sections = [
            "# Research Report\n",
            
            "## Executive Summary\n" + (report.executive_summary or "N/A"),
            
            "## Key Findings\n" + (report.key_findings or "N/A"),
            
            "## Detailed Analysis"
        ]
        
        # Add detailed analysis sections
        for section in report.detailed_analysis:
            if section["content"]:
                sections.append(f"### {section['title']}\n{section['content']}")
                
                if section["sources"]:
                    sources = "\n".join([f"- {source}" for source in section["sources"]])
                    sections.append(f"**Sources:**\n{sources}")
        
        # Add limitations
        sections.append("## Limitations and Further Research\n" + (report.limitations or "N/A"))
        
        return AIMessage(content="\n\n".join(sections))
    
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
        """Process a message using the deep research system with proper state management."""
        print("\n=== STARTING DEEP RESEARCH ===")
        print(f"Research Topic: {message}")
        
        # Convert chat history to messages
        history_messages = self._convert_history_to_messages(chat_history)
        
        # Add the current message
        history_messages.append(HumanMessage(content=message))
        
        # Create initial state with full conversation history
        initial_state = ResearchState(
            messages=history_messages,  # Include full history instead of just current message
            research_plan=None,
            report=None,
            next_step="research_manager"
        )
        # # Create initial state using MessagesState
        # initial_state = ResearchState(
        #     messages=[HumanMessage(content=message)],
        #     research_plan=None,
        #     report=None,
        #     next_step="research_manager"
        # )
        
        # Run workflow with optional tracing
        config = {"callbacks": [self.tracer]} if self.tracer else {}
        result = self.workflow.invoke(initial_state, config=config)
        
        print("\n=== RESEARCH COMPLETED ===")
        
        # Write the final report to a file
        try:
            with open("final_report.md", "w") as f:
                f.write(result["messages"][-1].content)
            print("Report saved to final_report.md")
        except Exception as e:
            print(f"Could not save report to file: {e}")
        
        # Return the final report
        return result["messages"][-1].content