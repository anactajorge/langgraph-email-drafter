import os
from typing import TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field


"""
todolist:
graph logic = mostly done
test = not yet
add a saving mechanism like sqllite = possible
"""

# email drafter 
# node drafter (llm) (generates a email draft )
# node evaluator (llm) (evaluates an email draft, return a score)
# conditional function (if score greater than 8 then send email, else go back to node drafter)

# start -> drafter -> evaluator -> conditional function -> drafter or end

llm = ChatGroq(model="openai/gpt-oss-20b") # 

class Evaluation(BaseModel):
    score: int = Field(ge=1, le=10, description="Score from 1 to 10 evaluating the draft quality.")
    critique: str = Field(description="Constructive feedback explaining what to improve.")

class AgentState(TypedDict):
    current_draft: str
    draft_score: int
    draft_topic: str
    feedback:str
    final_email: str

def drafter(state: AgentState) -> dict:
    """A node the helps a user create a email draft about a certain topic"""
    system_prompt = SystemMessage(
        content="You are Drafter, a helpful writing assistant. You are going to help the user draft an email."
    )

    user_prompt = HumanMessage(
        content=f"Please write an email draft about: {state['draft_topic']}"
    )

    response = llm.invoke([system_prompt, user_prompt])
    return {"current_draft":str(response.content)}

def evaluator(state: AgentState) -> dict:
    """A node the evaluates the drafter nodes response"""
    evaluator_llm = llm.with_structured_output(Evaluation)

    system_prompt = SystemMessage(
            content="""You are Evaluator,You are going to evaluate the current draft an email. and you will return a score 1-10,
            reply with only a 1-10        
            """
        )
    user_prompt = HumanMessage(
            content=f"the current draft is {state['current_draft']}"
        )
    result: Evaluation = evaluator_llm.invoke([system_prompt, user_prompt])
    return {"draft_score": result.score}

def finalizer(state: AgentState) -> dict:
    """Seals the approved draft into final_email."""
    return {"final_email": state["current_draft"]}

def routing_node(state: AgentState) -> Literal["drafter_node", "end"]:
    """routing node to end or route back to drafter"""
    if state["draft_score"] < 8:
        return "drafter_node"
    else:
        return "finalizer"

graph = StateGraph(AgentState)

graph.add_node("drafter", drafter)
graph.add_node("evaluator", evaluator)

graph.add_edge(START, "drafter")
graph.add_edge("drafter", "evaluator")

graph.add_conditional_edges(
    "evaluator",
    routing_node,
    {
        "drafter_node": drafter,
        "finalize": finalizer,
    }
)

graph.add_edge("finalize", END)

app = graph.compile() 

def run_agent():
    print("\n=== Drafting Assistant ===")
    
    while True:
        user_input = input("\nEnter email topic (or 'quit' to exit): ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break
        if not user_input:
            continue

        # Pass a plain string matching AgentState['draft_topic']
        result = app.invoke({"draft_topic": user_input})
        
        print(f"\n[Evaluator Score: {result['draft_score']}/10]")
        print("\n=== FINAL EMAIL ===")
        print(result["final_email"])

if __name__ == "__main__":
    run_agent() 
 

    



    