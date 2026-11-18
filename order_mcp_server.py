import re
from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

mcp = FastMCP("OrderSupportServer")

# Тестовая база заказов (в рабочей среде соединение открывается только для чтения)
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
    # 1. Проверяем правильность написания номера заказа
    try:
        validated = OrderLookupArgs(order_id=order_id)
    except ValueError as e:
        return {
            "success": False,
            "error_type": "VALIDATION_ERROR",
            "message_for_model": str(e),
        }

    # 2. Ищем заказ в базе данных
    order = MOCK_ORDERS_DB.get(validated.order_id)
    if not order:
        return {
            "success": False,
            "error_type": "NOT_FOUND",
            "message_for_model": f"Заказ {validated.order_id} не найден в базе. Уточните номер у клиента.",
        }

    # 3. ПРОВЕРКА ПРАВ ДОСТУПА В КОДЕ (защита от просмотра чужих заказов)
    if order["customer_id"] != authenticated_customer_id:
        return {
            "success": False,
            "error_type": "ACCESS_DENIED",
            "message_for_model": (
                f"Заказ {validated.order_id} оформлен на другого человека. "
                f"Сообщите клиенту, что доступ к этим данным закрыт."
            ),
        }

    # 4. Возвращаем только разрешенные поля (без служебных идентификаторов базы)
    return {
        "success": True,
        "order_id": validated.order_id,
        "status": order["status"],
        "delivery_window": order["delivery_window"],
        "items_count": order["items_count"],
        "total_rub": order["total_rub"],
    }
