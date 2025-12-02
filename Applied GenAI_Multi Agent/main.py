import os
import json
import sys
from langgraph_flow import build_workflow
from typing import Dict, Any

# --- 1. Environment Setup ---

# Ensure you have set your OPENAI_API_KEY environment variable
if 'OPENAI_API_KEY' not in os.environ:
    print("❌ FATAL: OPENAI_API_KEY environment variable not set.")
    print("Please set it in your terminal: export OPENAI_API_KEY='sk-...'")
    sys.exit(1)


def run_test_scenario(scenario_name: str, query: str) -> Dict[str, Any]:
    """Runs a single query through the multi-agent system."""
    print(f"\n🚀 Running Scenario: {scenario_name}")
    print(f"❓ Query: {query}")
    print("-" * 60)

    # Initialize the workflow
    app = build_workflow()

    # Initial state
    initial_state = {
        "query": query,
        "customer_context": {},
        "intermediate_steps": [],
        "next_action": "START",
        "final_response": ""
    }

    # Execute the graph
    # recursion_limit=15 allows for complex router loops (Router <-> Data Agent)
    try:
        final_state = app.invoke(initial_state, {"recursion_limit": 15})
        return final_state
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        return initial_state


# --- 2. Test Scenarios (Aligned with database_setup.py) ---

# Based on database_setup.py:
# ID 1: John Doe (Active)
# ID 3: Bob Johnson (Disabled)
# ID 7: Edward Norton (Active) - Let's use him for billing issues

test_scenarios = {
    # Scenario 1: Simple Query
    # Flow: Router -> Data Agent -> Router -> Support Agent
    "Simple_Query": "Get customer information for ID 5",

    # Scenario 2: Coordinated Query (Context + Advice)
    # Flow: Router -> Data Agent (fetch info) -> Router -> Support Agent (give advice based on 'disabled' status)
    "Coordinated_Query": "I am customer ID 3. Why can't I login?",

    # Scenario 3: Escalation (Urgency Detection)
    # Flow: Router (detects 'charged twice') -> Support Agent (Escalation response)
    # "Escalation_Urgent": "I've been charged twice for my subscription! Refund me immediately! (ID 7)",

    # Scenario 3: Complex Query
    # Flow: Router -> Data Agent (fetch info) -> Router -> Support Agent (Escalation response)
    "Complex_Query": "Show me all active customers who have open tickets",

    # Scenario 4: Multi-Intent / Complex
    # Flow: Router -> Data Agent (Update) -> Router -> Support (Confirm)
    # Note: Requires the Data Agent to correctly pick the 'update_customer' tool
    "Multi_Intent_Update": "Update the email for customer ID 1 to 'john.new@email.com'.",
}

# --- 3. Execution Loop ---

results = {}
print("=" * 80)
print("🤖 MULTI-AGENT CUSTOMER SERVICE SYSTEM - TEST SUITE")
print("=" * 80)

for name, query in test_scenarios.items():
    results[name] = run_test_scenario(name, query)

# --- 4. Final Report Generation (Deliverable Format) ---

print("\n\n" + "#" * 80)
print("## 📊 Final Test Report & A2A Logs")
print("#" * 80)

for name, result in results.items():
    query_text = test_scenarios[name]
    print(f"\n### 🧪 Scenario: {name}")
    print(f"**Query:** \"{query_text}\"")
    print("\n**1. 🤝 Agent-to-Agent (A2A) Communication Log:**")

    # Filter and print only clear A2A logs
    steps = result.get('intermediate_steps', [])
    if not steps:
        print("  (No steps recorded - execution might have failed)")

    for step in steps:
        # Only print our formatted logs from langgraph_flow.py
        if isinstance(step, str):
            clean_step = step.replace("[A2A LOG]", "").strip()
            print(f"  - {clean_step}")

    # Final Response
    print("\n**2. 💬 Final Response to Customer:**")
    response = result.get('final_response', "No response generated.")
    print(f"> {response}")

    # Data Context (Proof of MCP usage)
    print("\n**3. 💾 Final Data Context (MCP Artifacts):**")
    context = result.get('customer_context', {})
    print(f"```json\n{json.dumps(context, indent=2)}\n```")
    print("---")

# --- Conclusion (Example for Deliverable 3) ---

print("\n\n" + "#" * 80)
print("## Conclusion and Learning")
print("#" * 80)

print("""
**Learning Summary:**
Implementing the multi-agent system with LangGraph (Option B) provided a clear, state-machine approach for A2A coordination. The AgentState TypedDict served as the shared state/message-passing structure, allowing agents to read and write information (e.g., the Data Agent writes to `customer_context`, and the Support Agent reads it). The Router Agent effectively implemented the task allocation and negotiation by using conditional edges (`route_decision`), enabling multi-step flows like: Router -> Data Agent -> Router (to check if more steps are needed) -> Support Agent.

**Challenges:**
The main challenge was ensuring the Router Agent's output was consistently parsable (`DATA_AGENT: ...`). A minor challenge was integrating the **MCP tools**, which required careful definition using LangChain's `bind_tools` and the `ToolExecutor` to correctly invoke the Python functions defined in `mcp_server.py`. The use of LLMs for routing decisions, while flexible, required robust prompt engineering to prevent agents from getting stuck in a loop or deviating from the prescribed A2A protocol.
""")