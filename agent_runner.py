import json
from fastmcp import Client
from openai import AsyncOpenAI
from order_mcp_server import mcp  # Импортируем экземпляр сервера (или подключаемся по URL)


async def run_support_agent_via_mcp(
    openai_client: AsyncOpenAI,
    user_message: str,
    session_customer_id: str,
    max_steps: int = 3,
) -> str:
    input_messages = [
        {"role": "system", "content": "Проверяй заказы через функцию get_order_status."},
        {"role": "user", "content": user_message},
    ]

    # Подключаемся к серверу MCP как клиент
    async with Client(mcp) as mcp_client:
        # 1. Автоматически забираем список доступных функций с сервера MCP
        mcp_tools = await mcp_client.list_tools()

        # Формируем схему для OpenAI на лету (скрывая служебное поле authenticated_customer_id)
        openai_tools = []
        for tool in mcp_tools:
            schema = tool.inputSchema.copy()
            schema["properties"].pop("authenticated_customer_id", None)
            if "authenticated_customer_id" in schema.get("required", []):
                schema["required"].remove("authenticated_customer_id")

            openai_tools.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            })

        # 2. Запускаем цикл обработки вызовов
        for _ in range(max_steps):
            response = await openai_client.responses.create(
                model="gpt-4.1-mini",
                input=input_messages,
                tools=openai_tools,
            )

            tool_calls = [item for item in response.output if item.type == "function_call"]
            if not tool_calls:
                return response.output_text

            input_messages.extend(response.output)

            for call in tool_calls:
                args = json.loads(call.arguments)
                # Подставляем защищенный идентификатор клиента перед отправкой в MCP
                args["authenticated_customer_id"] = session_customer_id

                # 3. Вызываем функцию через протокол MCP
                mcp_result = await mcp_client.call_tool(call.name, args)

                input_messages.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": mcp_result.content[0].text,
                })

    return "Превышено допустимое число шагов. Переключаю на специалиста."