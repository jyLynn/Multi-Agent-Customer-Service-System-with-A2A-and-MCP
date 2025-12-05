# main.py
import asyncio
from typing import Dict, Any

import httpx
from termcolor import colored
from a2a.client import ClientConfig, ClientFactory, create_text_message_object
from a2a.types import (
    AgentCard,
    TransportProtocol,
)
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

ROUTER_AGENT_URL = "http://127.0.0.1:10032"


class A2ASimpleClient:
    """A2A Simple to call A2A servers."""

    def __init__(self, default_timeout: float = 240.0):
        self._agent_info_cache: dict[str, dict[str, Any] | None] = {}
        self.default_timeout = default_timeout

    async def create_task(self, agent_url: str, message: str) -> str:
        """Send a message to an A2A agent and return a safe text response."""
        timeout_config = httpx.Timeout(
            timeout=self.default_timeout,
            connect=10.0,
            read=self.default_timeout,
            write=10.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            # Fetch or reuse agent card
            if agent_url in self._agent_info_cache and self._agent_info_cache[agent_url] is not None:
                agent_card_data = self._agent_info_cache[agent_url]
            else:
                agent_card_response = await httpx_client.get(
                    f"{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}"
                )
                agent_card_data = agent_card_response.json()
                self._agent_info_cache[agent_url] = agent_card_data

            agent_card = AgentCard(**agent_card_data)

            config = ClientConfig(
                httpx_client=httpx_client,
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                use_client_preference=True,
            )

            factory = ClientFactory(config)
            client = factory.create(agent_card)

            message_obj = create_text_message_object(content=message)

            responses = []
            async for response in client.send_message(message_obj):
                responses.append(response)

            if not responses:
                return "No response received (empty responses list)."

            first = responses[0]
            if not (isinstance(first, tuple) and len(first) > 0):
                return f"Unexpected response shape: {first}"

            task = first[0]

            # 1) If the task has an error, raise it immediately.
            if getattr(task, "error", None) is not None:
                return f"Task error from agent: {task.error}"

            # 2) Happy path: Try to retrieve text from artifacts.
            try:
                artifacts = getattr(task, "artifacts", None)
                if artifacts and len(artifacts) > 0:
                    parts = getattr(artifacts[0], "parts", None)
                    if parts and len(parts) > 0:
                        root = getattr(parts[0], "root", None)
                        text = getattr(root, "text", None)
                        if text:
                            return text
            except Exception:
                # Ignore exceptions and proceed to fallback.
                pass

            # 3) Fallback: Retrieve text from the last message in task.history.
            history = getattr(task, "history", []) or []
            if history:
                last_msg = history[-1]
                parts = getattr(last_msg, "parts", None)
                if parts and len(parts) > 0:
                    root = getattr(parts[0], "root", None)
                    text = getattr(root, "text", None)
                    if text:
                        return text

            # 4) If all else fails, dump the entire task.
            return f"Task completed but no text found.\nRaw task: {task!r}"


a2a_client = A2ASimpleClient()


async def ask_router(query: str):
    print(colored("\n" + "=" * 80, "magenta"))
    print(colored("👤 USER: ", "cyan", attrs=["bold"]) + query)
    print(colored("=" * 80, "magenta"))

    try:
        response = await a2a_client.create_task(ROUTER_AGENT_URL, query)
        print(colored("🤖 ROUTER AGENT (final answer):", "green", attrs=["bold"]))
        print(response)
        print()
        return response
    except Exception as e:
        print(colored(f"❌ Error calling Router Agent: {e}", "red"))
        return None


async def run_assignment_scenarios():
    # Testing
    await ask_router("Get customer information for ID 5")
    # await ask_router("I'm customer 1 and need help upgrading my account")
    # await ask_router("Show me all active customers who have open tickets")
    await ask_router("My ID is 5. I've been charged twice, please refund immediately!")
    await ask_router("Update my email to new@email.com and show my ticket history. My customer ID is 1.")


if __name__ == "__main__":
    asyncio.run(run_assignment_scenarios())
