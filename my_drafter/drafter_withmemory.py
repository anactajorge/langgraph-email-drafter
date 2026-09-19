import os
import sqlite3
from typing import TypedDict, Literal
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

load_dotenv()

# LLM setup
llm = ChatGroq(model="openai/gpt-oss-20b")


# Structured output schema for the evaluator
class Evaluation(BaseModel):
    score: int = Field(ge=1, le=10, description="Score from 1 to 10 evaluating the draft quality.")
    feedback: str = Field(description="Constructive feedback explaining what to improve.")


# Shared state tracked across graph execution
class AgentState(TypedDict):
    current_draft: str
    draft_score: int
    draft_topic: str
    feedback: str
    final_email: str
    revision_count: int


# Node: Generates the initial draft or rewrites it based on feedback
def drafter(state: AgentState) -> dict:
    system_prompt = SystemMessage(
        content="You are Drafter, a helpful writing assistant. You are going to help the user draft an email."
    )

    if state.get("feedback"):
        user_prompt = HumanMessage(
            content=f"Please rewrite this email draft about {state['draft_topic']}. "
                    f"Here is the previous draft:\n{state['current_draft']}\n\n"
                    f"Here is the feedback to improve it:\n{state['feedback']}"
        )
    else:
        user_prompt = HumanMessage(
            content=f"Please write an email draft about: {state['draft_topic']}"
        )

    current_count = state.get("revision_count", 0) + 1
    response = llm.invoke([system_prompt, user_prompt])
    
    return {
        "current_draft": str(response.content),
        "revision_count": current_count
    }


# Node: Evaluates draft quality and outputs a score with feedback
def evaluator(state: AgentState) -> dict:
    evaluator_llm = llm.with_structured_output(Evaluation)

    system_prompt = SystemMessage(
        content="You are Evaluator. Evaluate the email draft, return a score 1-10 and feedback."
    )
    user_prompt = HumanMessage(
        content=f"Topic: {state['draft_topic']}\nCurrent Draft:\n{state['current_draft']}"
    )
    result: Evaluation = evaluator_llm.invoke([system_prompt, user_prompt])
    return {"draft_score": result.score, "feedback": result.feedback}


# Node: Finalizes the accepted draft
def finalizer(state: AgentState) -> dict:
    return {"final_email": state["current_draft"]}


# Conditional edge: Decides whether to revise again or finalize
def routing_node(state: AgentState) -> Literal["drafter", "finalize"]:
    # Stop revision loop if max attempts reached or score is sufficient (>= 8)
    if state.get("revision_count", 0) >= 3:
        return "finalize"
    if state.get("draft_score", 0) < 8:
        return "drafter"
    return "finalize"


# Build the workflow graph
graph = StateGraph(AgentState)

graph.add_node("drafter", drafter)
graph.add_node("evaluator", evaluator)
graph.add_node("finalize", finalizer)

graph.add_edge(START, "drafter")
graph.add_edge("drafter", "evaluator")

graph.add_conditional_edges(
    "evaluator",
    routing_node,
    {
        "drafter": "drafter",
        "finalize": "finalize",
    }
)
graph.add_edge("finalize", END)

# Persistent state storage using SQLite
conn = sqlite3.connect("drafts_memory.db", check_same_thread=False)
checkpointer = SqliteSaver(conn)

# Compile graph with persistence enabled
app = graph.compile(checkpointer=checkpointer)


# CLI interface to run or resume sessions
def run_agent():
    print("\n=== Email Drafting Assistant ===")
    
    # Identify or resume session by thread ID
    thread_id = input("Enter Session / User ID: ").strip()
    if not thread_id:
        print("A session ID is required.")
        return

    config = {"configurable": {"thread_id": thread_id}}

    # Load existing state if this thread ID has been used before
    existing_state = app.get_state(config).values

    if existing_state.get("final_email"):
        print(f"\n[Resumed Session: {thread_id}]")
        print(f"Current Draft on file:\n{existing_state['final_email']}\n")
        prompt_label = "Enter revision instructions or a new topic (or 'quit'): "
    else:
        print(f"\n[New Session: {thread_id}]")
        prompt_label = "Enter email topic (or 'quit'): "

    # Main interaction loop
    while True:
        user_input = input(f"\n{prompt_label}").strip()
        
        if user_input.lower() in ["exit", "quit"]:
            print("Session saved. Goodbye!")
            break
            
        if not user_input:
            continue

        # Pass user input as revision feedback if draft exists, otherwise as new topic
        if existing_state.get("current_draft"):
            payload = {
                "feedback": user_input,
                "revision_count": existing_state.get("revision_count", 0)
            }
        else:
            payload = {
                "draft_topic": user_input,
                "revision_count": 0
            }

        result = app.invoke(payload, config=config)
        existing_state = result

        print("\n--- Generated Email ---")
        print(result.get("final_email") or result.get("current_draft"))
        prompt_label = "Enter changes/feedback (or 'quit'): "


if __name__ == "__main__":
    run_agent()