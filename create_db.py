
import sqlite3

MOCK_ORDERS_DB = {
    "ORD-44102": {
        "customer_id": "CUST-100",
        "status": "В пути (передан курьеру)",
        "delivery_window": "10:00 - 14:00",
        "items_count": 2,
        "total_rub": 8450,
    },
    "ORD-55101": {
        "customer_id": "CUST-200",
        "status": "Готов к отгрузке (упакован)",
        "delivery_window": "Завтра, 12:00 - 18:00",
        "items_count": 1,
        "total_rub": 12900,
    },
    "ORD-55102": {
        "customer_id": "CUST-200",
        "status": "На комплектации на складе",
        "delivery_window": "Ожидает сборки",
        "items_count": 4,
        "total_rub": 34200,
    },
    "ORD-60200": {
        "customer_id": "CUST-300",
        "status": "Доставлен в пункт выдачи",
        "delivery_window": "Хранение до 30 октября",
        "items_count": 2,
        "total_rub": 64000,
    },
    "ORD-99801": {
        "customer_id": "CUST-777",
        "status": "Ожидает возврата средств",
        "delivery_window": "Отменен",
        "items_count": 5,
        "total_rub": 145000,
    },
}

conn = sqlite3.connect("orders_mock.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        status TEXT NOT NULL,
        delivery_window TEXT,
        items_count INTEGER NOT NULL,
        total_rub INTEGER NOT NULL
    )
""")

for order_id, order in MOCK_ORDERS_DB.items():
    cursor.execute("""
        INSERT OR REPLACE INTO orders (
            order_id,
            customer_id,
            status,
            delivery_window,
            items_count,
            total_rub
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        order_id,
        order["customer_id"],
        order["status"],
        order["delivery_window"],
        order["items_count"],
        order["total_rub"],
    ))

conn.commit()

print("Создана SQLite БД: orders_mock.db")
print("Количество заказов:", cursor.execute(
    "SELECT COUNT(*) FROM orders"
).fetchone()[0])

conn.close()
