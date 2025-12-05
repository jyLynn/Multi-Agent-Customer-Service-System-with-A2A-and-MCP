# mcp_server.py
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "support.db")

# ========= 1. Database lookup =========

def show_database():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Customers
    cursor.execute("""SELECT * FROM customers;""")

    # Tickets
    cursor.execute("""SELECT * FROM tickets;""")


    conn.close()

    print("✅ Database showcase - ", DB_PATH)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert SQLite row to dictionary."""
    return {k: row[k] for k in row.keys()}


# ========= REQUIRED MCP TOOL =========

def get_customer(customer_id: int) -> Dict[str, Any]:
    """get_customer(customer_id) - uses customers.id"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"success": False, "error": f"Customer {customer_id} not found"}
        return {"success": True, "customer": row_to_dict(row)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_customers(status: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """list_customers(status, limit) - uses customers.status"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if status:
            if status not in ["active", "disabled"]:
                return {"success": False, "error": "Status must be 'active' or 'disabled'"}
            query = "SELECT * FROM customers WHERE status = ? ORDER BY id LIMIT ?"
            cur.execute(query, (status, limit))
        else:
            query = "SELECT * FROM customers ORDER BY id LIMIT ?"
            cur.execute(query, (limit,))

        rows = cur.fetchall()
        conn.close()
        return {
            "success": True,
            "count": len(rows),
            "customers": [row_to_dict(r) for r in rows],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_customer(customer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """update_customer(customer_id, data) - uses customers fields"""
    allowed_fields = {"name", "email", "phone", "status"}

    # Filter invalid keys
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return {"success": False, "error": "No valid fields to update"}

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check existence
        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "error": f"Customer {customer_id} not found"}

        # Build dynamic update query
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [customer_id]

        query = f"UPDATE customers SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        cur.execute(query, params)
        conn.commit()

        # Return updated customer
        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        updated = cur.fetchone()
        conn.close()

        return {"success": True, "customer": row_to_dict(updated)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_ticket(customer_id: int, issue: str, priority: str = "medium") -> Dict[str, Any]:
    """create_ticket(customer_id, issue, priority) - uses tickets fields"""
    try:
        if priority not in ("low", "medium", "high"):
            return {"success": False, "error": "priority must be low/medium/high"}
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "error": f"Customer {customer_id} not found"}

        cur.execute(
            "INSERT INTO tickets (customer_id, issue, status, priority) VALUES (?, ?, 'open', ?)",
            (customer_id, issue, priority),
        )
        ticket_id = cur.lastrowid
        conn.commit()

        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        conn.close()

        return {"success": True, "ticket": row_to_dict(row)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_customer_history(customer_id: int) -> Dict[str, Any]:
    """get_customer_history(customer_id) - uses tickets.customer_id"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check customer exists
        cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "error": f"Customer {customer_id} not found"}

        cur.execute("SELECT * FROM tickets WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,))
        rows = cur.fetchall()
        conn.close()
        return {
            "success": True,
            "count": len(rows),
            "tickets": [row_to_dict(r) for r in rows],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========= MCP Protocol Layer =========

app = Flask(__name__)
CORS(app)

MCP_TOOLS = [
    {
        "name": "get_customer",
        "description": "Retrieve a customer by ID",
        "inputSchema": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "list_customers",
        "description": "List customers, optionally by status, with optional limit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "disabled"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "update_customer",
        "description": "Update customer fields",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "data": {"type": "object"},
            },
            "required": ["customer_id", "data"],
        },
    },
    {
        "name": "create_ticket",
        "description": "Create a support ticket for a customer",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "issue": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["customer_id", "issue"],
        },
    },
    {
        "name": "get_customer_history",
        "description": "Get all tickets for a customer",
        "inputSchema": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
]


def create_sse_message(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def handle_initialize(message: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "customer-service-mcp-server", "version": "1.0.0"},
        },
    }


def handle_tools_list(message: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {"tools": MCP_TOOLS},
    }


# Map tool names to actual Python functions
TOOL_FUNCTIONS = {
    "get_customer": lambda args: get_customer(args["customer_id"]),
    "list_customers": lambda args: list_customers(
        status=args.get("status"),
        limit=args.get("limit", 50)
    ),
    "update_customer": lambda args: update_customer(
        args["customer_id"],
        args["data"]
    ),
    "create_ticket": lambda args: create_ticket(
        args["customer_id"],
        args["issue"],
        args.get("priority", "medium")
    ),
    "get_customer_history": lambda args: get_customer_history(
        args["customer_id"]
    ),
}


def handle_tools_call(message: Dict[str, Any]) -> Dict[str, Any]:
    params = message.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {}) or {}

    if tool_name not in TOOL_FUNCTIONS:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
        }

    try:
        result = TOOL_FUNCTIONS[tool_name](arguments)
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            },
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"},
        }


def process_mcp_message(message: Dict[str, Any]) -> Dict[str, Any]:
    method = message.get("method")
    if method == "initialize":
        return handle_initialize(message)
    if method == "tools/list":
        return handle_tools_list(message)
    if method == "tools/call":
        return handle_tools_call(message)
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


@app.route("/mcp", methods=["POST"])
def mcp_endpoint():
    message = request.get_json()

    def generate():
        try:
            print(f"📥 MCP method: {message.get('method')}")
            response = process_mcp_message(message)
            yield create_sse_message(response)
        except Exception as e:
            yield create_sse_message({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(e)},
            })

    return Response(generate(), mimetype="text/event-stream")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "server": "mcp-customer-service"})


if __name__ == "__main__":
    # show_database()
    print("✅ Starting MCP server on http://127.0.0.1:5000/mcp")
    app.run(host="127.0.0.1", port=5000, debug=False)

