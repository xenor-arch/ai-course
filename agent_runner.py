
import json
from fastmcp import Client
from openai import AsyncOpenAI
from order_mcp_server import mcp


async def run_support_agent_via_mcp(
    openai_client: AsyncOpenAI,
    user_message: str,
    session_customer_id: str,
    max_steps: int = 3,
) -> str:

    input_messages = [
        {
            "role": "system",
            "content": "Проверяй заказы через функцию get_order_status."
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    # Подключаемся к MCP-серверу
    async with Client(mcp) as mcp_client:

        # 1. Получаем список функций MCP-сервера
        mcp_tools = await mcp_client.list_tools()

        # 2. Формируем JSON-схемы для OpenAI
        openai_tools = []

        for tool in mcp_tools:
            schema = tool.inputSchema.copy()
            schema["properties"] = schema.get("properties", {}).copy()

            # Удаляем служебный параметр из схемы
            schema["properties"].pop("authenticated_customer_id", None)

            if "authenticated_customer_id" in schema.get("required", []):
                schema["required"].remove("authenticated_customer_id")

            openai_tools.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            })

        # 3. Цикл обработки запросов (максимум 3 шага)
        for _ in range(max_steps):

            response = await openai_client.responses.create(
                model="gpt-4.1-mini",
                input=input_messages,
                tools=openai_tools,
            )

            # Проверяем, вызвала ли модель какие-либо функции
            tool_calls = [
                item for item in response.output
                if item.type == "function_call"
            ]

            if not tool_calls:
                return response.output_text

            input_messages.extend(response.output)

            # 4. Выполняем вызовы MCP
            for call in tool_calls:

                args = json.loads(call.arguments)

                # Принудительно подставляем ID клиента из текущей сессии
                args["authenticated_customer_id"] = session_customer_id

                mcp_result = await mcp_client.call_tool(
                    call.name,
                    args,
                )

                input_messages.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": mcp_result.content[0].text,
                })

    return "Превышено допустимое число шагов. Переключаю на специалиста."
