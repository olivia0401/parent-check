"""
LangGraph re-implementation of the scam-analysis agent.

The original hand-rolled `for _ in range(2)` loop in agent.py is kept as a
readable contrast. This version expresses the exact same behaviour as an
explicit LangGraph state machine:

        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             │
    ┌────────┐   wants a tool?   ┌────────┐           │
    │ reason │ ───────────────▶  │ tools  │ ──────────┘
    └────────┘                   └────────┘
        │  final verdict / done
        ▼
       END

Why this is worth doing over the ad-hoc loop:
  * Named nodes + a conditional router make the control flow explicit and
    inspectable instead of buried in a for-loop.
  * The turn budget is enforced by the graph's edges, not an off-by-one
    range() — the router simply refuses to go back to `reason` once the
    budget is spent.
  * A checkpointer records each step, so a run can be inspected or resumed.
    We use an in-memory saver and delete the run's thread when it finishes
    (a scam check is single-shot). In production you would swap in
    LangGraph's SqliteSaver / PostgresSaver — this project already runs
    Postgres — so runs survive a restart.

Per-request dependencies (the llm client and the language's RAG engine) are
passed through the run *config*, not the graph *state*: state is serialized
by the checkpointer, and these objects aren't serializable (and shouldn't be
persisted anyway).

The safety invariants are unchanged and still live in agent.py:
  * risk can only ever be pushed UP (pick_higher_risk),
  * any failure falls back to the rule-based verdict (returns None),
  * user text is wrapped as data to blunt prompt injection.
"""
import logging
import uuid
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .agent import (
    build_analysis_prompt,
    decide_actions,
    parse_ai_reply,
    pick_higher_risk,
)
from .tools import TOOL_DECLARATIONS, run_tools_parallel

logger = logging.getLogger(__name__)

# The model gets at most this many reasoning turns: one to (optionally) call
# tools, one to give its final verdict. Enforced by the router below.
MAX_REASON_TURNS = 2


class AgentState(TypedDict):
    """Everything a single analysis run carries through the graph."""
    content: str
    lang: str
    existing_risk: str
    messages: list           # Gemini-format conversation ("contents")
    tools_called: list        # names of tools the model invoked, for the UI
    turns: int                # how many times `reason` has run
    pending_calls: Optional[list]   # tool calls waiting to be executed
    result: Optional[dict]    # final verdict dict, or None to fall back
    done: bool                # set once we have a terminal answer


def _final(existing_risk, parsed, tools_called):
    """Build the terminal result dict, applying the only-ever-escalate rule."""
    if parsed is None:
        # Model found nothing new — keep the rule-based floor untouched.
        risk = existing_risk
        reason = advice = ""
    else:
        risk = pick_higher_risk(existing_risk, parsed["ai_risk"])
        reason = parsed["reason"]
        advice = parsed["advice"]
    return {
        "ai_risk": risk,
        "reason": reason,
        "advice": advice,
        "actions": decide_actions(risk),
        "tools_called": tools_called,
    }


def reason_node(state: AgentState, config) -> dict:
    """Ask the model what to do next: call a tool, or give a verdict."""
    llm = config["configurable"]["llm"]
    turns = state["turns"] + 1
    response = llm.generate_with_tools(state["messages"], TOOL_DECLARATIONS)

    # Request failed → give up, fall back to the rule-based verdict.
    if response is None:
        return {"turns": turns, "done": True, "result": None}

    # Model produced a verdict → parse it and finish.
    if response["type"] == "text":
        parsed = parse_ai_reply(response["text"], state["lang"])
        return {
            "turns": turns,
            "done": True,
            "result": _final(state["existing_risk"], parsed, state["tools_called"]),
        }

    # Model asked for tool(s) → record them and hand off to the tools node.
    calls = response["calls"]
    return {
        "turns": turns,
        "messages": state["messages"] + [{"role": "model", "parts": response["raw_parts"]}],
        "pending_calls": calls,
        "tools_called": state["tools_called"] + [c["name"] for c in calls],
    }


def tools_node(state: AgentState, config) -> dict:
    """Run every tool the model asked for, then feed results back as one turn."""
    rag = config["configurable"]["rag"]
    results = run_tools_parallel(
        state["pending_calls"], rag, state["lang"], state["content"]
    )
    responses = [
        {"functionResponse": {"name": r["name"], "response": r["response"]}}
        for r in results
    ]
    return {
        "messages": state["messages"] + [{"role": "user", "parts": responses}],
        "pending_calls": None,
    }


def _route_after_reason(state: AgentState) -> str:
    """Decide where to go after the model reasons."""
    if state.get("done"):
        return END
    if state.get("pending_calls"):
        # Only loop back for tools if we still have a turn left to read them.
        if state["turns"] >= MAX_REASON_TURNS:
            return END  # budget spent with no verdict → fall back (result=None)
        return "tools"
    return END


def _build_graph(checkpointer):
    graph = StateGraph(AgentState)
    graph.add_node("reason", reason_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("reason")
    graph.add_conditional_edges("reason", _route_after_reason, {"tools": "tools", END: END})
    graph.add_edge("tools", "reason")
    return graph.compile(checkpointer=checkpointer)


# Compile the graph once per process; it holds no per-request state.
_COMPILED = None


def _get_graph():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = _build_graph(MemorySaver())
    return _COMPILED


def analyze(content, lang, existing_risk, llm, rag):
    """
    Drop-in replacement for agent.analyze(), backed by the LangGraph state
    machine. Same signature, same return contract (a result dict, or None
    when the AI step can't run / fails).
    """
    if not llm.available:
        return None

    graph = _get_graph()
    initial: AgentState = {
        "content": content,
        "lang": lang,
        "existing_risk": existing_risk,
        "messages": [{"role": "user", "parts": [{"text": build_analysis_prompt(content, lang)}]}],
        "tools_called": [],
        "turns": 0,
        "pending_calls": None,
        "result": None,
        "done": False,
    }
    # A fresh thread id isolates this run's checkpoints; llm/rag ride along in
    # `configurable` so they're available to the nodes but never serialized.
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id, "llm": llm, "rag": rag}}

    try:
        final_state = graph.invoke(initial, config)
        return final_state.get("result")
    except Exception:
        # Same fail-safe as the original: a broken AI step must never lower
        # the rule-based verdict. Log the type (never the user's text).
        logger.warning("LangGraph AI step failed (keeping rule-based result)", exc_info=True)
        return None
    finally:
        # A scam check is single-shot; drop the run's checkpoints so the
        # in-memory saver can't grow without bound.
        try:
            graph.checkpointer.delete_thread(thread_id)
        except Exception:
            pass
