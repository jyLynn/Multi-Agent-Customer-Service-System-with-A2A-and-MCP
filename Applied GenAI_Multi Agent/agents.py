import os
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("OPENAI_API_KEY environment variable not set.")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# --- Base Agent Class ---

class BaseAgent:
    def __init__(self, name: str, system_message: str, tools: List[Any] = None):
        self.name = name
        self.system_message = system_message
        self.tools = tools or []
        self._setup_agent()

    def _setup_agent(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.system_message),
                ("user", "{input}"),
            ]
        )

        if self.tools:
            # 有 MCP 工具的 Agent（Data Agent）
            self.runnable = prompt | llm.bind_tools(self.tools)
        else:
            # 纯对话 Agent（Router / Support）
            self.runnable = prompt | llm | StrOutputParser()

    def invoke(self, input_data: Dict[str, Any]):
        return self.runnable.invoke(input_data)



class RouterAgent(BaseAgent):
    def __init__(self):
        system_message = (
            "You are the **Router Agent (Orchestrator)**.\n"
            "You never talk to the end user. Your only job is to decide which agent "
            "should act next based on:\n"
            "  (1) the user query, and\n"
            "  (2) the current shared state (customer_context).\n\n"
            "=== POSSIBLE NEXT STEPS ===\n"
            "- 'DATA_AGENT' → Call the Customer Data Agent (which will use MCP tools).\n"
            "- 'SUPPORT_AGENT' → Call the Support Agent (which will talk to the user).\n"
            "- 'COMPLETE' → Workflow is done, final answer already produced.\n"
            "- 'ESCALATE' → Treat like 'SUPPORT_AGENT' but with elevated urgency.\n\n"
            "=== WHAT'S IN CURRENT CONTEXT ===\n"
            "- customer_context.get('data_query_result'): result from Data Agent "
            "  (any DB lookup or update).\n"
            "- customer_context.get('support_request'): Support Agent asking for more data, "
            "  e.g. 'NEED_BILLING_INFO', 'NEED_CUSTOMER_PROFILE', "
            "'NEED_TICKET_SUMMARY'.\n\n"
            "=== GENERIC ROUTING RULES (NO HARDCODED QUERIES) ===\n"
            "1) If the Support Agent has asked for more data via 'support_request' and "
            "   there is NO new 'data_query_result' yet → route to 'DATA_AGENT'.\n\n"
            "2) If there is fresh 'data_query_result' but no open 'support_request' that "
            "   requires more DB work → route to 'SUPPORT_AGENT' to transform data "
            "   into a human-facing answer.\n\n"
            "3) If there is NEITHER 'support_request' NOR 'data_query_result':\n"
            "   - If the query is **primarily about data** (lookups, updates, lists, "
            "     status, ticket history, etc.)\n"
            "     → route to 'DATA_AGENT'.\n"
            "   - If the query is **ambiguous, multi-intent, or policy/negotiation-"
            "     heavy** (e.g. cancellation, refund, billing dispute, complaints)\n"
            "     → route to 'SUPPORT_AGENT' first so it can decide what it needs.\n\n"
            "4) If the driver indicates that a final user-facing answer has already "
            "   been produced, you may output 'COMPLETE'.\n\n"
            "You MUST output exactly ONE word:\n"
            "  'DATA_AGENT', 'SUPPORT_AGENT', 'COMPLETE', or 'ESCALATE'.\n\n"
            "Current Context (Python dict string): {current_state}"
        )
        super().__init__("Router Agent", system_message, tools=[])

    def invoke(self, current_state: Dict[str, Any], query: str) -> str:
        return self.runnable.invoke(
            {
                "input": f"User Query: {query}",
                "current_state": str(current_state),
            }
        )



class CustomerDataAgent(BaseAgent):
    def __init__(self, mcp_tools: List[Any]):
        system_message = (
            "You are the **Customer Data Agent**.\n"
            "You never answer the user directly. Your ONLY job is to choose and call "
            "exactly one MCP tool that makes progress on the query.\n\n"
            "You have access to generic tools (names may vary slightly at runtime):\n"
            "- get_customer(customer_id: int): fetch a single customer's profile.\n"
            "- list_customers(status: str, limit: int): list customers with filters.\n"
            "- update_customer(customer_id: int, data: dict): update fields like email, phone, status.\n"
            "- create_ticket(customer_id: int, issue: str, priority: str): create a support ticket.\n"
            "- get_customer_history(customer_id: int): fetch all tickets for a customer.\n\n"
            "=== GENERIC STRATEGY ===\n"
            "- If the query is about a specific customer (contains an ID) and wants "
            "  'information', 'details', or a 'profile' → use `get_customer`.\n"
            "- If the Support Agent has requested a customer profile (the context says "
            "  something like NEED_CUSTOMER_PROFILE or similar), you SHOULD use "
            "  `get_customer` instead of `get_customer_history`.\n"
            "- If the query wants a list or segment of customers (e.g. all active, all disabled) "
            "  → use `list_customers`.\n"
            "- If the query wants to change customer data (e.g. update email, disable account) "
            "  → use `update_customer` with an appropriate `data` dict.\n"
            "- If the query is about creating a new issue or complaint → use `create_ticket`.\n"
            "- If the query is about a customer's tickets or history → use "
            "  `get_customer_history`.\n\n"
            "Complex multi-step reporting (e.g. combining customers and tickets) is handled "
            "by the Python orchestrator. Your job is to choose ONE best tool call "
            "for the current step, with precise arguments.\n\n"
            "Do NOT ask the user clarifying questions. Use the text of the query and any "
            "existing context to infer the correct parameters."
        )
        super().__init__("Customer Data Agent", system_message, tools=mcp_tools)



class SupportAgent(BaseAgent):
    def __init__(self):
        system_message = (
            "You are the **Support Agent**.\n"
            "You NEVER call tools. You only:\n"
            "  - read the original user query, and\n"
            "  - read the 'customer_context' (data_query_result, support_request, etc.),\n"
            "and then decide whether you can answer or need more data.\n\n"
            "=== TWO MODES ===\n"
            "1) If you have enough information in 'customer_context' to answer:\n"
            "   - Produce a clear, friendly, professional answer to the user in natural language.\n"
            "   - Summarize any DB results (customer profile, ticket summary, updates, etc.).\n"
            "   - Confirm updates explicitly (e.g., new email).\n\n"
            "2) If you DO NOT yet have enough information and need the Data Agent to query something:\n"
            "   - DO NOT write a normal answer.\n"
            "   - Instead, output EXACTLY one line of the form:\n"
            "       'ROUTING_REQUEST: <REQUEST_CODE>'\n"
            "   - <REQUEST_CODE> is a short code you invent describing what you need, e.g.:\n"
            "       'NEED_CUSTOMER_PROFILE', 'NEED_TICKET_SUMMARY',\n"
            "       'NEED_ACTIVE_CUSTOMER_LIST', 'NEED_OPEN_TICKET_STATUS', etc.\n"
            "   - Do NOT add any extra text or explanation.\n\n"
            "Examples:\n"
            "- If the query says: 'Show me all active customers who have open tickets', and "
            "  customer_context has no data yet, you might output:\n"
            "      'ROUTING_REQUEST: NEED_CUSTOMER_AND_TICKET_SUMMARY'\n"
            "ONLY when you have enough data should you produce a full natural-language answer.\n\n"
            "Customer Context (Python dict string): {customer_context}"
        )
        super().__init__("Support Agent", system_message, tools=[])

    def invoke(self, query: str, context: Dict[str, Any]) -> str:
        return self.runnable.invoke(
            {
                "input": f"Customer Query: {query}",
                "customer_context": str(context),
            }
        )
