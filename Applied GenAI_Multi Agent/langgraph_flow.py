import operator
from typing import TypedDict, Annotated, List, Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage

from agents import RouterAgent, CustomerDataAgent, SupportAgent
from mcp_server import MCP_TOOLS, list_customers, get_customer_history


# --- 1. Shared State ---

class AgentState(TypedDict):
    query: str
    next_action: str
    customer_context: Dict[str, Any]
    intermediate_steps: Annotated[List[str], operator.add]
    final_response: str


# --- 2. Init Agents & tools ---

router_agent = RouterAgent()
data_agent = CustomerDataAgent(MCP_TOOLS)
support_agent = SupportAgent()

tools_map = {tool.__name__: tool for tool in MCP_TOOLS}


# --- 3. Node Functions ---

def call_router(state: AgentState) -> Dict[str, Any]:
    print("\n[A2A LOG] ➡️ Router Agent analyzing...")

    if state.get("final_response"):
        return {"next_action": "COMPLETE"}

    current_context = state.get("customer_context", {}) or {}
    if "support_request" in current_context:
        request_code = current_context["support_request"]
        log_entry = f"Router hard-rule: support_request present ({request_code}) → DATA_AGENT"
        print(f"[A2A LOG] 🧭 {log_entry}")
        return {
            "next_action": "DATA_AGENT",
            "intermediate_steps": [log_entry],
        }

    router_output = router_agent.invoke(current_context, state["query"])

    clean_output = router_output.strip().upper()
    if "DATA_AGENT" in clean_output:
        next_action = "DATA_AGENT"
    elif "SUPPORT_AGENT" in clean_output:
        next_action = "SUPPORT_AGENT"
    elif "ESCALATE" in clean_output:
        next_action = "SUPPORT_AGENT"
    elif "COMPLETE" in clean_output:
        next_action = "COMPLETE"
    else:
        next_action = "SUPPORT_AGENT"

    log_entry = f"Router Decision: {next_action} (Raw: {router_output})"
    print(f"[A2A LOG] 🧭 {log_entry}")

    return {
        "next_action": next_action,
        "intermediate_steps": [log_entry],
    }


def call_data_agent(state: AgentState) -> Dict[str, Any]:
    print("\n[A2A LOG] ➡️ Customer Data Agent working...")

    user_query = state["query"].lower()
    # response = data_agent.invoke({"input": state["query"]})
    ctx = state.get("customer_context", {}) or {}
    support_request = ctx.get("support_request", "")

    response = data_agent.invoke(
        {
            "input": (
                f"User query: {state['query']}\n"
                f"Support request (if any): {support_request}\n"
                f"Existing context: {ctx}"
            )
        }
    )

    if not isinstance(response, AIMessage) or not getattr(response, "tool_calls", None):
        log_msg = "Data Agent did not make a tool call."
        print(f"[A2A LOG] ⚠️ {log_msg}")
        new_ctx = dict(state.get("customer_context", {}))
        new_ctx["data_query_result"] = {"error": "Data Agent failed to choose a tool."}
        return {"customer_context": new_ctx, "intermediate_steps": [log_msg]}

    tool_call = response.tool_calls[0]
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]

    print(f"[A2A LOG] 🔧 Tool Selected: {tool_name} with args: {tool_args}")

    if support_request and "PROFILE" in support_request.upper():
        if tool_name != "get_customer" and "customer_id" in tool_args and "get_customer" in tools_map:
            print("[A2A LOG] 🔁 Override: support_request asks for PROFILE, "
                  "forcing tool to get_customer instead of", tool_name)
            tool_name = "get_customer"
            tool_args = {"customer_id": tool_args["customer_id"]}

    if tool_name == "list_customers" and "ticket" in user_query:
        print("[A2A LOG] 🔁 Detected list_customers + tickets scenario, composing summary...")

        try:
            active_or_filtered = list_customers(**tool_args)
        except Exception as e:
            log_msg = f"Error in list_customers: {e}"
            print(f"[A2A LOG] ❌ {log_msg}")
            new_ctx = dict(state.get("customer_context", {}))
            new_ctx["data_query_result"] = {"error": log_msg}
            return {"customer_context": new_ctx, "intermediate_steps": [log_msg]}

        summary = []
        for c in active_or_filtered:
            cid = c["id"]
            history = get_customer_history(cid)
            open_tickets = [t for t in history if t.get("status") == "open"]
            total_tickets = len(history)
            if "open" in user_query:
                # 如果 query 提到 open tickets，就只保留有 open 的客户
                if open_tickets:
                    summary.append(
                        {
                            "customer_id": cid,
                            "name": c["name"],
                            "total_tickets": total_tickets,
                            "open_ticket_count": len(open_tickets),
                            "open_tickets": open_tickets,
                        }
                    )
            else:
                summary.append(
                    {
                        "customer_id": cid,
                        "name": c["name"],
                        "total_tickets": total_tickets,
                        "open_ticket_count": len(open_tickets),
                        "tickets": history,
                    }
                )

        result_data = {
            "type": "customer_ticket_summary",
            "customers": summary,
        }
        print(f"[A2A LOG] ✅ Composed customer_ticket_summary for {len(summary)} customers.")

        new_ctx = dict(state.get("customer_context", {}))
        new_ctx["data_query_result"] = result_data
        new_ctx.pop("support_request", None)
        return {
            "customer_context": new_ctx,
            "intermediate_steps": ["Executed list_customers + get_customer_history (composed)"],
        }

    if tool_name in tools_map:
        try:
            selected_tool = tools_map[tool_name]
            result_data = selected_tool(**tool_args)
            print(f"[A2A LOG] ✅ Tool Success. Result preview: {str(result_data)[:120]}...")
        except Exception as e:
            result_data = {"error": f"Tool execution failed: {e}"}
            print(f"[A2A LOG] ❌ Tool Error: {e}")
    else:
        result_data = {"error": f"Tool {tool_name} not found in tools_map"}
        print(f"[A2A LOG] ❌ Tool {tool_name} not found.")

    new_ctx = dict(state.get("customer_context", {}))
    new_ctx["data_query_result"] = result_data
    new_ctx.pop("support_request", None)

    return {
        "customer_context": new_ctx,
        "intermediate_steps": [f"Executed {tool_name}"],
    }


def call_support_agent(state: AgentState) -> Dict[str, Any]:
    print("\n[A2A LOG] ➡️ Support Agent formulating response...")

    context = state.get("customer_context", {})
    raw_output = support_agent.invoke(state["query"], context).strip()

    if raw_output.startswith("ROUTING_REQUEST:"):
        request_code = raw_output.split(":", 1)[1].strip()
        print(f"[A2A LOG] 🔁 Support requested more data: {request_code}")

        new_ctx = dict(context)
        new_ctx["support_request"] = request_code

        return {
            "customer_context": new_ctx,
            "next_action": "ROUTER",
            "intermediate_steps": [f"Support requested data: {request_code}"],
        }

    final_response = raw_output
    print("[A2A LOG] 🗣️ Final Response Generated.")

    return {
        "final_response": final_response,
        "next_action": "COMPLETE",
        "intermediate_steps": ["Support Agent responded."],
    }


# --- 4. Routing ---

def route_decision(state: AgentState) -> str:
    action = state["next_action"]
    if action == "DATA_AGENT":
        return "data_agent"
    elif action == "SUPPORT_AGENT":
        return "support_agent"
    elif action == "COMPLETE":
        return "end"
    else:
        return "support_agent"


def support_route_decision(state: AgentState) -> str:
    """
    After Support Agent runs, decide whether to go back to Router or end.
    """
    action = state.get("next_action", "")
    if action == "ROUTER":
        return "router"
    else:
        return "end"


# --- 5. Build Graph ---

def build_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", call_router)
    workflow.add_node("data_agent", call_data_agent)
    workflow.add_node("support_agent", call_support_agent)

    workflow.set_entry_point("router")

    # Router -> Data / Support / End
    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "data_agent": "data_agent",
            "support_agent": "support_agent",
            "end": END,
        },
    )

    workflow.add_edge("data_agent", "router")

    workflow.add_conditional_edges(
        "support_agent",
        support_route_decision,
        {
            "router": "router",
            "end": END,
        },
    )

    return workflow.compile()
