
import re
import sqlite3
from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

mcp = FastMCP("OrderSupportServer")


class OrderLookupArgs(BaseModel):
    order_id: str = Field(
        description="Номер заказа строго по образцу ORD-XXXXX (например, ORD-44102)"
    )

    @field_validator("order_id")
    @classmethod
    def validate_order_prefix(cls, v: str) -> str:
        cleaned = v.strip().upper()

        if not re.match(r"^ORD-\d{4,6}$", cleaned):
            raise ValueError(
                f"Неверный формат '{v}'. Номер заказа должен состоять из букв 'ORD-' "
                f"и 4-6 цифр (например, ORD-44102). Исправьте значение и вызовите функцию заново."
            )

        return cleaned


@mcp.tool(
    name="get_order_status",
    description="Возвращает состояние доставки и сумму заказа по его номеру.",
)
def get_order_status(
    order_id: Annotated[str, "Номер заказа по образцу ORD-XXXXX"],
    authenticated_customer_id: Annotated[
        str, "Служебный идентификатор клиента (подставляется программой)"
    ],
) -> dict:

    # 1. Проверяем формат номера заказа через Pydantic
    try:
        validated = OrderLookupArgs(order_id=order_id)
    except ValueError as e:
        return {
            "success": False,
            "error_type": "VALIDATION_ERROR",
            "message_for_model": str(e),
        }

    # 2. Подключаемся к SQLite строго в режиме чтения
    try:
        conn = sqlite3.connect(
            "file:orders_mock.db?mode=ro",
            uri=True
        )
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # 3. Ищем заказ по номеру
        cursor.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (validated.order_id,)
        )

        order = cursor.fetchone()
        conn.close()

    except sqlite3.Error as e:
        return {
            "success": False,
            "error_type": "DATABASE_ERROR",
            "message_for_model": f"Ошибка при чтении базы данных: {e}",
        }

    # 4. Проверяем, существует ли заказ
    if not order:
        return {
            "success": False,
            "error_type": "NOT_FOUND",
            "message_for_model": (
                f"Заказ {validated.order_id} не найден в базе. "
                f"Уточните номер у клиента."
            ),
        }

    # 5. Проверяем права доступа
    if order["customer_id"] != authenticated_customer_id:
        return {
            "success": False,
            "error_type": "ACCESS_DENIED",
            "message_for_model": (
                f"Заказ {validated.order_id} оформлен на другого человека. "
                f"Сообщите клиенту, что доступ к этим данным закрыт."
            ),
        }

    # 6. Возвращаем только разрешенные поля
    return {
        "success": True,
        "order_id": validated.order_id,
        "status": order["status"],
        "delivery_window": order["delivery_window"],
        "items_count": order["items_count"],
        "total_rub": order["total_rub"],
    }
