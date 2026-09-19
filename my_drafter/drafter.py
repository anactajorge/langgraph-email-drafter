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
load_dotenv() 

llm = ChatGroq(model="openai/gpt-oss-20b") 


class Evaluation(BaseModel):
    score: int = Field(ge=1, le=10, description="Score from 1 to 10 evaluating the draft quality.")
    feedback: str = Field(description="Constructive feedback explaining what to improve.")

class AgentState(TypedDict):
    current_draft: str
    draft_score: int
    draft_topic: str
    feedback:str
    final_email: str
    #revision_count: int

def drafter(state: AgentState) -> dict:
    """A node that helps a user create an email draft about a certain topic"""
    system_prompt = SystemMessage(
        content="You are Drafter, a helpful writing assistant. You are going to help the user draft an email."
    )

    # LOGICAL FIX: We check if there is existing feedback. 
    # If there is, we tell the LLM to improve its previous draft using the evaluator's feedback.
    # Otherwise, it will just write the exact same email forever!
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
        #"revision_count": current_count
        }

def evaluator(state: AgentState) -> dict:
    """A node the evaluates the drafter nodes response"""
    evaluator_llm = llm.with_structured_output(Evaluation)

    system_prompt = SystemMessage(
            content="""You are Evaluator,You are going to evaluate the current draft an email. and you will return a score 1-10 and give feedback,
            reply with only a 1-10        
            """
        )
    user_prompt = HumanMessage(
            content=f"""
            Topic: {state['draft_topic']}
            Current Draft:{state['current_draft']}.
            """
        )
    result: Evaluation = evaluator_llm.invoke([system_prompt, user_prompt])
    return {"draft_score": result.score, "feedback": result.feedback}

def finalizer(state: AgentState) -> dict:
    """Seals the approved draft into final_email."""
    return {"final_email": state["current_draft"]} #"draft_topic": state["draft_topic"]}

def routing_node(state: AgentState) -> Literal["drafter", "finalize"]:
    """routing node to end or route back to drafter"""
    if state["draft_score"] < 8:
        return "drafter"
    else:
        return "finalize"

    """# Stop revision loop once cap of 3 drafts is reached
    if state.get("revision_count", 0) >= 3:
        return "finalize"

    # Re-draft if score is below 8
    if state.get("draft_score", 0) < 8:
        return "drafter"

    return "finalize" """

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
        result = app.invoke(
            {
                "draft_topic": user_input,
                #"revision_count": 0,
            }
        )
        #Print out the State to check the Results
        print(f"\nTopic:    {result.get('draft_topic')}")
        print(f"Score:    {result.get('draft_score')}/10")
        print(f"Feedback: {result.get('feedback')}")
        print(f"Email:\n{result.get('final_email')}")


        
        """print(f"\n[Evaluator Score: {result['draft_score']}/10]")
        print("\n=== FINAL EMAIL ===")
        print(result["final_email"]) """

if __name__ == "__main__":
    run_agent() 
 

    



    