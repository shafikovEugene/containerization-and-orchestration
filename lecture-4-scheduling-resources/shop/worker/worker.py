import os
import time

import psycopg

DB_HOST = os.getenv("DB_HOST", "postgres-rw")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASSWORD = os.getenv("DB_PASSWORD", "shop")


def process_orders():
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    ) as conn:
        orders = conn.execute(
            """
            SELECT id, item, quantity
            FROM orders
            WHERE processed = FALSE
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            """
        ).fetchall()

        for order_id, item, quantity in orders:
            print(
                f"Processing order {order_id}: "
                f"{item} x {quantity}",
                flush=True,
            )

            conn.execute(
                "UPDATE orders SET processed = TRUE WHERE id = %s",
                (order_id,),
            )


if __name__ == "__main__":
    while True:
        try:
            process_orders()
        except psycopg.OperationalError as exc:
            print(f"Database unavailable: {exc}", flush=True)
        except Exception as exc:
            print(f"Worker error: {exc}", flush=True)

        time.sleep(5)