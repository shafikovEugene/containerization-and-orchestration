
import os
import time

import psycopg
from flask import Flask, jsonify, request

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASSWORD = os.getenv("DB_PASSWORD", "shop")


def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=3,
    )


def init_db():
    for attempt in range(30):
        try:
            with get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        item TEXT NOT NULL,
                        quantity INTEGER NOT NULL CHECK (quantity > 0),
                        processed BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            print("Database initialized", flush=True)
            return
        except psycopg.OperationalError:
            if attempt == 29:
                raise
            print("Waiting for PostgreSQL...", flush=True)
            time.sleep(2)


@app.get("/health")
def health():
    if os.getenv("HEALTH_FAIL", "false").lower() == "true":
        return jsonify(status="unhealthy"), 503
    return "ok", 200


@app.post("/order")
def create_order():
    data = request.get_json(silent=True) or {}

    item = data.get("item")
    quantity = data.get("quantity", 1)

    if not isinstance(item, str) or not item.strip():
        return jsonify(error="item must be a non-empty string"), 400

    # bool является подклассом int в Python, поэтому исключаем его явно.
    if type(quantity) is not int or quantity <= 0:
        return jsonify(error="quantity must be a positive integer"), 400

    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO orders (item, quantity)
                VALUES (%s, %s)
                RETURNING id, item, quantity, processed, created_at
                """,
                (item.strip(), quantity),
            ).fetchone()

        return jsonify({
            "id": row[0],
            "item": row[1],
            "quantity": row[2],
            "processed": row[3],
            "created_at": row[4].isoformat(),
        }), 201

    except psycopg.Error:
        app.logger.exception("Failed to create order")
        return jsonify(error="database unavailable"), 503


@app.get("/orders")
def list_orders():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, item, quantity, processed, created_at
                FROM orders
                ORDER BY id
            """).fetchall()

        return jsonify([
            {
                "id": row[0],
                "item": row[1],
                "quantity": row[2],
                "processed": row[3],
                "created_at": row[4].isoformat(),
            }
            for row in rows
        ])

    except psycopg.Error:
        app.logger.exception("Failed to list orders")
        return jsonify(error="database unavailable"), 503


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
