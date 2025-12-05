# agents.py
import os
from termcolor import colored

import google.generativeai as genai
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams
import sys

# ========= Configure API Key and MCP URL =========

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if 'GOOGLE_API_KEY' not in os.environ:
    print("No GOOGLE_API_KEY found.")
    GOOGLE_API_KEY = input("Please enter your GOOGLE API key : ").strip()

    if not GOOGLE_API_KEY:
        print("❌ FATAL: Invalid API key.")
        sys.exit(1)

    # Temporarily set for this session
    os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY
    print("API key set successfully for this run.")

genai.configure(api_key=GOOGLE_API_KEY)
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

# The MCP server defaults to local port 5000
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:5000/mcp")

print(colored(f"✅ Google Generative AI & MCP configured. MCP_SERVER_URL={MCP_SERVER_URL}", "green"))

# ========= Customer Data Agent =========

customer_data_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="customer_data_agent",
    tools=[
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_SERVER_URL
            )
        )
    ],
    instruction="""
        You are the Customer Data Agent.
        
        You ONLY interact with the customer database via MCP tools:
        - get_customer(customer_id)
        - list_customers(status, limit)
        - update_customer(customer_id, data)
        - get_customer_history(customer_id)
        - create_ticket(customer_id, issue, priority)
        
        Your responsibilities:
        - Fetch customer profiles and ticket history
        - Update customer fields safely (validate fields before calling update)
        - Summarize raw JSON results into concise, structured text
        - When performing a task, explicitly call the right MCP tool and then explain the result.
        
        If you cannot find a customer, clearly say so.
        Always be precise about IDs, statuses, and priorities.
        """,
)

# ========= Support Agent =========

support_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="support_agent",
    tools=[
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_SERVER_URL
            )
        )
    ],
    instruction="""
        You are the Support Agent.
        
        You handle general customer support:
        - Account issues (upgrade, cancellation, refund, etc.)
        - Ticket creation and follow-up
        - Explaining policies and next steps
        
        When you need customer context (profile or history):
        - You can call MCP tools (get_customer, get_customer_history, create_ticket, update_customer)
          to simulate asking the Customer Data Agent.
        
        You must:
        - Detect urgency (e.g., double charge + refund request = high-priority)
        - Decide when to escalate or create a ticket (using create_ticket) and explain this clearly
        - Provide clear, empathetic responses suitable for a real customer.
        
        Your answers should be friendly but professional, and reflect any data you retrieved.
        """,
)

# ========= Router Agent =========

router_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="router_agent",
    tools=[
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_SERVER_URL
            )
        )
    ],
    instruction="""
    You are the Router Agent in a multi-agent customer service system.

    Your responsibilities:
    1. Receive customer queries.
    2. Detect user intents (customer lookup, account issues, billing, profile updates,
       ticket creation, multi-intent requests).
    3. Use the appropriate MCP-backed tools to interact with the customer database.
    4. For multi-step or multi-intent queries, call multiple tools and merge the results.
    5. NEVER hallucinate customer data — always use tools to read/write from the DB.

    Available tools (IMPORTANT):
    - get_customer(customer_id: int)
        → Fetch a single customer's full record.
    - list_customers(status: Optional['active'|'disabled'], limit: int = 50)
        → List customers, optionally filtered by status.
    - update_customer(customer_id: int, data: dict)
        → Update customer fields such as email, phone, or status.
    - create_ticket(customer_id: int, issue: str, priority: 'low'|'medium'|'high' = 'medium')
        → Create a support ticket for a customer.
    - get_customer_history(customer_id: int)
        → Get all tickets for a given customer.

    Routing rules:
    - If the user asks for a specific customer by ID → use get_customer.
    - If the user wants a list of customers (e.g., all active) → use list_customers.
    - If the user wants to change profile details → use update_customer and then
      confirm the updated fields.
    - If the user reports a problem or incident → use create_ticket (priority 'high'
      for urgent issues like billing problems and refunds).
    - If the user asks for their ticket history → use get_customer_history.
    - For complex queries (e.g., "all active customers who have open tickets"),
      you may need multiple tool calls:
        • First list active customers
        • Then get ticket histories and filter for open tickets.

    Your output:
    - Provide a clean, human-friendly response summarizing the results of your tool calls.
    - When helpful, you may include key fields (e.g., name, email, status, ticket status).
    """,
)

print("Router Agent created.")

print(colored("✅ Customer Data Agent & Support Agent created", "green"))
