"""
database.py

Persistent storage layer for OCR5.

Stores processed invoices so OCR5 can remember:
- previous invoices
- extracted fields
- confidence scores
- processing history

Uses SQLite because it requires no external database server.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


DATABASE_PATH = Path("invoice_database.db")


def get_connection():
    """
    Creates and returns a database connection.
    """
    return sqlite3.connect(DATABASE_PATH)


def initialise_database():
    """
    Creates database tables if they do not already exist.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            supplier TEXT,
            invoice_date TEXT,
            amount REAL,
            currency TEXT,

            confidence INTEGER,

            image_path TEXT,

            created_at TEXT
        )
        """
    )

    connection.commit()
    connection.close()


def save_invoice(
    supplier: str | None,
    invoice_date: str | None,
    amount: float | None,
    currency: str,
    confidence: int,
    image_path: str,
):
    """
    Saves an extracted invoice into the database.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO invoices
        (
            supplier,
            invoice_date,
            amount,
            currency,
            confidence,
            image_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            supplier,
            invoice_date,
            amount,
            currency,
            confidence,
            image_path,
            datetime.now().isoformat(),
        ),
    )

    connection.commit()
    connection.close()


def get_all_invoices():
    """
    Returns all stored invoices.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM invoices
        ORDER BY created_at DESC
        """
    )

    invoices = cursor.fetchall()

    connection.close()

    return invoices


def search_supplier(supplier: str):
    """
    Finds previous invoices from the same supplier.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM invoices
        WHERE supplier LIKE ?
        ORDER BY created_at DESC
        """,
        (f"%{supplier}%",),
    )

    results = cursor.fetchall()

    connection.close()

    return results


if __name__ == "__main__":
    initialise_database()

    print("OCR5 database created successfully.")
