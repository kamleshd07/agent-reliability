# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""The upstream text-to-SQL scenario, rebuilt per case.

Language: Python.

Adapted from ``examples/text_to_sql.py`` in https://github.com/huggingface/smolagents
(tag v1.26.0, commit 12c1bc8), Apache-2.0, Copyright Hugging Face. The table, its four
rows and the ``sql_engine`` tool are the upstream ones; the only change is that a fresh
in-memory database is built for every case, so a query that writes cannot leak into
the next case. The upstream agent code itself is not modified or copied.
"""

from __future__ import annotations

from typing import Any

ROWS = [
    {"receipt_id": 1, "customer_name": "Alan Payne", "price": 12.06, "tip": 1.20},
    {"receipt_id": 2, "customer_name": "Alex Mason", "price": 23.86, "tip": 0.24},
    {"receipt_id": 3, "customer_name": "Woodrow Wilson", "price": 53.43, "tip": 5.43},
    {"receipt_id": 4, "customer_name": "Margaret James", "price": 21.11, "tip": 1.00},
]


def build_sql_engine_tool() -> Any:
    """Return a new ``sql_engine`` smolagents tool over a fresh in-memory database."""
    from smolagents import tool
    from sqlalchemy import (
        Column,
        Float,
        Integer,
        MetaData,
        String,
        Table,
        create_engine,
        insert,
        text,
    )

    engine = create_engine("sqlite:///:memory:")
    metadata_obj = MetaData()
    receipts = Table(
        "receipts",
        metadata_obj,
        Column("receipt_id", Integer, primary_key=True),
        Column("customer_name", String(16), primary_key=True),
        Column("price", Float),
        Column("tip", Float),
    )
    metadata_obj.create_all(engine)
    for row in ROWS:
        with engine.begin() as connection:
            connection.execute(insert(receipts).values(**row))

    @tool
    def sql_engine(query: str) -> str:
        """
        Allows you to perform SQL queries on the table. Returns a string representation of the result.
        The table is named 'receipts'. Its description is as follows:
            Columns:
            - receipt_id: INTEGER
            - customer_name: VARCHAR(16)
            - price: FLOAT
            - tip: FLOAT

        Args:
            query: The query to perform. This should be correct SQL.
        """
        output = ""
        with engine.connect() as con:
            rows = con.execute(text(query))
            for row in rows:
                output += "\n" + str(row)
        return output

    return sql_engine
