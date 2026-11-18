
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

    # Общая статистика
    total_cost = 0
    total_function_calls = {}

    for i, ticket in enumerate(tickets, 1):
        print("\n" + "=" * 70)
        print(f"[{i}/{len(tickets)}] {ticket['ticket_id']}")
        print("=" * 70)

        stats = {}

        try:
            result = await run_support_agent_via_mcp(
                openai_client=client,
                user_message=ticket["text"],
                session_customer_id=ticket["session_customer_id"],
                max_steps=3,
                stats=stats,
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

        finally:
            # Подсчитываем вызовы функций
            function_calls = stats.get("function_calls", {})

            for name, count in function_calls.items():
                total_function_calls[name] = (
                    total_function_calls.get(name, 0) + count
                )

            # Рассчитываем стоимость обращения
            input_tokens = stats.get("input_tokens", 0)
            output_tokens = stats.get("output_tokens", 0)
            cached_tokens = stats.get("cached_tokens", 0)

            input_cost = (
                (input_tokens - cached_tokens) * 0.40
                + cached_tokens * 0.10
            ) / 1_000_000

            output_cost = (
                output_tokens * 1.60
            ) / 1_000_000

            ticket_cost = input_cost + output_cost
            total_cost += ticket_cost

            print("\nСтатистика обращения:")
            print(f"Вызовы функций: {function_calls}")
            print(
                f"Всего вызовов функций: "
                f"{sum(function_calls.values())}"
            )
            print(f"Входные токены: {input_tokens}")
            print(f"Выходные токены: {output_tokens}")
            print(f"Кешированные токены: {cached_tokens}")
            print(f"Стоимость обращения: ${ticket_cost:.6f}")

    # Сохраняем результаты
    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print("\n" + "=" * 70)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"Всего обращений: {len(tickets)}")
    print(f"Успешно обработано: {sum(r['success'] for r in results)}")
    print(f"Ошибок выполнения: {sum(not r['success'] for r in results)}")
    print("Результаты сохранены в test_results.json")

    # Итоговая статистика
    print("\n" + "=" * 70)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)

    print("\nКоличество вызовов функций:")

    for name, count in total_function_calls.items():
        print(f"{name}: {count}")

    print(
        f"Всего вызовов функций: "
        f"{sum(total_function_calls.values())}"
    )

    print(f"\nОбщая стоимость прогона: ${total_cost:.6f}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
