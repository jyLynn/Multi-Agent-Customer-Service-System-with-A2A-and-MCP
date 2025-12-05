import a2a.client.client

import sys

from a2a.client import client as real_client_module
from a2a.client.card_resolver import A2ACardResolver


class PatchedClientModule:
    def __init__(self, real_module) -> None:
        for attr in dir(real_module):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(real_module, attr))
        self.A2ACardResolver = A2ACardResolver


patched_module = PatchedClientModule(real_client_module)
sys.modules['a2a.client.client'] = patched_module  # type: ignore

import asyncio

import uvicorn
from termcolor import colored

from google.adk import Runner
from a2a.server.apps import A2AStarletteApplication
from google.adk.a2a.executor.a2a_agent_executor import (
    A2aAgentExecutor,
    A2aAgentExecutorConfig,
)
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TransportProtocol,
)
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents import SequentialAgent

from agents import customer_data_agent, support_agent


def create_agent_a2a_server(agent, agent_card: AgentCard):
    """Create an A2A server"""
    runner = Runner(
        app_name=agent.name,
        agent=agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    config = A2aAgentExecutorConfig()
    executor = A2aAgentExecutor(runner=runner, config=config)
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    return A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

async def run_agent_server(agent, agent_card: AgentCard, port: int):
    """Start an A2A server on the specified port."""
    app = create_agent_a2a_server(agent, agent_card)
    config = uvicorn.Config(
        app.build(),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()

# ---------- Specialist 1: Customer Data Agent ----------
customer_data_agent_card = AgentCard(
    name="Customer Data Agent",
    url="http://127.0.0.1:10030",
    description="Specialist for customer data access via MCP",
    version="1.0",
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    preferred_transport=TransportProtocol.jsonrpc,
    skills=[
        AgentSkill(
            id="customer_data_ops",
            name="Customer Data Operations",
            description='Retrieve, update, and manage customer records using MCP tools. '
                'Supports customer lookup, updates, ticket creation, and '
                'ticket history retrieval.',
            examples=[
                "Get profile for customer ID 5 and summarize it.",
                "List all active customers with limit 20.",
                "Show ticket history for customer 1.",
                "Create ticket for customer 5"
            ],
            tags=['database', 'customer', 'records', 'support', 'MCP', 'tickets'],
        )
    ],
)

# ---------- Specialist 2: Support Agent ----------
support_agent_card = AgentCard(
    name="Support Agent",
    url="http://127.0.0.1:10031",
    description="General support specialist for customer issues",
    version="1.0",
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    preferred_transport=TransportProtocol.jsonrpc,
    skills=[
        AgentSkill(
            id="customer_support",
            name="Customer Support",
            description='Resolves general customer support issues, checks customer identity, '
                        'requests data from the Customer Data Agent, and escalates issues '
                        'by creating tickets when needed.',
            examples=[
                "Help customer 3 reset their email.",
                "Customer 5 cannot login, what should we do?",
                "Explain the account status for customer 7.",
                "File a support request for customer 2.",
                "Summarize the ticket history for customer 1."
            ],
            tags=['support', 'helpdesk', 'customer service', 'escalation'],
        )
    ],
)

# --- Remote A2A wrappers for the two specialist agents ---
# These two act as "proxies", using the A2A protocol to call services on ports 10030 / 10031.

remote_customer_data_agent = RemoteA2aAgent(
    name="customer_data_remote",
    description="Remote A2A client to Customer Data Agent",
    agent_card=f"http://127.0.0.1:10030{AGENT_CARD_WELL_KNOWN_PATH}",
)

remote_support_agent = RemoteA2aAgent(
    name="support_remote",
    description="Remote A2A client to Support Agent",
    agent_card=f"http://127.0.0.1:10031{AGENT_CARD_WELL_KNOWN_PATH}",
)


# ---------- Router / Orchestrator Agent  ----------
router_agent = SequentialAgent(
    name="router_agent",
    sub_agents=[
        remote_customer_data_agent,
        remote_support_agent,
    ],
)

router_agent_card = AgentCard(
    name="Router Agent",
    url="http://127.0.0.1:10032",
    description="Orchestrates customer queries across Customer Data Agent and Support Agent",
    version="1.0",
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    preferred_transport=TransportProtocol.jsonrpc,
    skills=[
        AgentSkill(
            id="route_customer_queries",
            name="Route Customer Queries",
            description=(
                "Receives end-user customer service queries and coordinates "
                "the Customer Data Agent and Support Agent using A2A."
            ),
            tags=["router", "orchestrator", "customer-service"],
            examples=[
                "Get customer information for ID 5.",
                "Update customer 7 email to [email protected]",
                "Show me all active customers who have open tickets.",
                "Create a ticket for customer 3",
                "I was double charged—help me",
            ],
        )
    ],
)



async def main():
    print(colored("🚀 Starting A2A servers...", "cyan"))

    tasks = [
        asyncio.create_task(
            run_agent_server(customer_data_agent, customer_data_agent_card, 10030)
        ),
        asyncio.create_task(
            run_agent_server(support_agent, support_agent_card, 10031)
        ),
        asyncio.create_task(
            run_agent_server(router_agent, router_agent_card, 10032)
        ),
    ]

    # Give Uvicorn a moment to start up.
    await asyncio.sleep(2)

    print(colored("✅ All A2A agent servers started!", "green"))
    print("   - Customer Data Agent: http://127.0.0.1:10030" + AGENT_CARD_WELL_KNOWN_PATH)
    print("   - Support Agent      : http://127.0.0.1:10031" + AGENT_CARD_WELL_KNOWN_PATH)
    print("   - Router Agent       : http://127.0.0.1:10032" + AGENT_CARD_WELL_KNOWN_PATH)

    # Suspend execution to keep the three servers running.
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("🛑 Shutting down A2A servers...")


if __name__ == "__main__":
    asyncio.run(main())