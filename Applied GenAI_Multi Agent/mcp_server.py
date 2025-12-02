import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime

DATABASE_NAME = "support.db"


def _get_db_connection():
    """Helper function to create a database connection."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# --- MCP Tool Implementations ---

def get_customer(customer_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single customer's information using their ID.
    Args:
        customer_id: The ID of the customer.
    """
    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email, phone, status, created_at, updated_at FROM customers WHERE id = ?",
            (customer_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_customers(status: str = 'active', limit: int = 10) -> List[Dict[str, Any]]:
    """
    Lists customers filtered by status.
    Args:
        status: The status to filter by ('active' or 'disabled').
        limit: Maximum number of customers to return.
    """
    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email, phone, status FROM customers WHERE status = ? LIMIT ?",
            (status, limit)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_customer(customer_id: int, email: str = None, phone: str = None, name: str = None, status: str = None) -> bool:
    """
    Updates a customer's record.
    Args:
        customer_id: The ID of the customer to update.
        email: (Optional) New email address.
        phone: (Optional) New phone number.
        name: (Optional) New name.
        status: (Optional) New status ('active' or 'disabled').
    """
    data = {}
    if email: data['email'] = email
    if phone: data['phone'] = phone
    if name: data['name'] = name
    if status: data['status'] = status

    if not data:
        return False

    set_clauses = []
    values = []

    for key, value in data.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)

    if not set_clauses:
        return False

    sql = f"UPDATE customers SET {', '.join(set_clauses)} WHERE id = ?"
    values.append(customer_id)

    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(values))
        conn.commit()
        # 返回 True 表示更新成功
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating customer {customer_id}: {e}")
        return False
    finally:
        conn.close()


def create_ticket(customer_id: int, issue: str, priority: str = 'medium') -> Optional[Dict[str, Any]]:
    """
    Creates a new support ticket.
    Args:
        customer_id: The ID of the customer creating the ticket.
        issue: Description of the issue.
        priority: Priority level ('low', 'medium', 'high'). Defaults to 'medium'.
    """
    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tickets (customer_id, issue, status, priority) VALUES (?, ?, ?, ?)",
            (customer_id, issue, 'open', priority)
        )
        ticket_id = cursor.lastrowid
        conn.commit()

        # Fetch back the created ticket to get the correct timestamp
        cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        new_ticket = cursor.fetchone()

        return dict(new_ticket) if new_ticket else None
    except Exception as e:
        print(f"Error creating ticket: {e}")
        return None
    finally:
        conn.close()


def get_customer_history(customer_id: int) -> List[Dict[str, Any]]:
    """
    Retrieves all tickets for a given customer ID.
    Args:
        customer_id: The ID of the customer.
    """
    conn = _get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, issue, status, priority, created_at FROM tickets WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()



# Export the tools
MCP_TOOLS = [
    get_customer,
    list_customers,
    update_customer,
    create_ticket,
    get_customer_history
]

