
import asyncio
import json
from openai import AsyncOpenAI

from agent_runner import run_support_agent_via_mcp
from dotenv import load_dotenv

load_dotenv()


async def main():
    client = AsyncOpenAI()

    # Загружаем обращения
    with open("tickets_with_tools.json", "r", encoding="utf-8") as f:
        tickets = json.load(f)

    print(f"Загружено обращений: {len(tickets)}")

    results = []

    for i, ticket in enumerate(tickets, 1):
        print("\n" + "=" * 70)
        print(f"[{i}/{len(tickets)}] {ticket['ticket_id']}")
        print("=" * 70)

        try:
            result = await run_support_agent_via_mcp(
                openai_client=client,
                user_message=ticket["text"],
                session_customer_id=ticket["session_customer_id"],
                max_steps=3,
            )

            print("Ответ агента:")
            print(result)

            results.append({
                "ticket_id": ticket["ticket_id"],
                "success": True,
                "response": result,
            })

        except Exception as e:
            print(f"ОШИБКА: {e}")

            results.append({
                "ticket_id": ticket["ticket_id"],
                "success": False,
                "error": str(e),
            })

    # Сохраняем результаты
    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print("\n" + "=" * 70)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"Всего обращений: {len(tickets)}")
    print(f"Успешно обработано: {sum(r['success'] for r in results)}")
    print(f"Ошибок выполнения: {sum(not r['success'] for r in results)}")
    print("Результаты сохранены в test_results.json")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
