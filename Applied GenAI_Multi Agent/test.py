# test_client.py
import json
import requests
from termcolor import colored

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

def send_mcp_message(method: str, params: dict = None, message_id: int = 1):
    message = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": method
    }
    if params:
        message["params"] = params

    print(colored("\n📤 Sending MCP Request:", "cyan", attrs=["bold"]))
    print(colored(json.dumps(message, indent=2), "cyan"))

    try:
        response = requests.post(
            f"{SERVER_URL}/mcp",
            json=message,
            stream=True,
            timeout=10
        )

        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode("utf-8")
            if line.startswith("data: "):
                payload = json.loads(line[6:])  # remove 'data: '
                print(colored("\n📥 Received MCP Response:", "green", attrs=["bold"]))
                print(colored(json.dumps(payload, indent=2), "green"))
                return payload

    except Exception as e:
        print(colored(f"\n Error: {e}", "red"))
        return None


if __name__ == "__main__":
    print(colored("=" * 60, "magenta"))
    print(colored("TEST 3: LIST ALL CUSTOMERS", "magenta", attrs=["bold"]))
    print(colored("=" * 60, "magenta"))

    list_response = send_mcp_message(
        method="tools/call",
        params={
            "name": "list_customers",
            "arguments": {}
        },
        message_id=3
    )

    # Correct extraction of MCP JSON result
    try:
        content = list_response["result"]["content"][0]
        result_json = content["json"]  # <-- NEW (correct)
    except:
        print(colored("\n Failed to parse tool response", "red"))
        result_json = None

    if result_json and result_json.get("success"):
        print(colored(f"\n {result_json['count']} customers found:", "green", attrs=["bold"]))

        for cust in result_json["customers"]:
            color = "green" if cust["status"] == "active" else "red"
            print(f"\nID: {cust['id']}")
            print(f"   Name: {cust['name']}")
            print(f"   Email: {cust['email']}")
            print(f"   Phone: {cust['phone']}")
            print(colored(f"   Status: {cust['status']}", color))
    else:
        print(colored("\n list_customers failed", "red"))
