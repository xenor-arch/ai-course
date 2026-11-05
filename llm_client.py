import logging
from enum import Enum
from typing import Literal, Type, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_client")

T = TypeVar("T", bound=BaseModel)


# --- 1. ПОЛЬЗОВАТЕЛЬСКИЕ ИСКЛЮЧЕНИЯ ---
class LLMBudgetExceededError(Exception):
    """Возникает при превышении заданного лимита расходов."""

class LLMRefusalError(Exception):
    """Возникает, когда модель отказывается выполнять запрос по правилам безопасности."""

class LLMOutputTruncatedError(Exception):
    """Возникает, когда ответ обрывается из-за нехватки лимита max_output_tokens."""


# --- 2. КОНТРОЛЛЕР РАСХОДОВ С УЧЕТОМ ТОКЕНОВ РАССУЖДЕНИЙ ---
class CostTracker:
    # Стоимость за 1 миллион токенов (в долларах США)
    PRICING_PER_1M = {
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1": {"input": 2.00, "output": 8.00},
        "o4-mini": {"input": 1.10, "output": 4.40},
    }

    def __init__(self, max_budget_usd: float = 5.0):
        self.max_budget_usd = max_budget_usd
        self.current_spend_usd = 0.0
        self.total_requests = 0

    def check_budget(self) -> None:
        if self.current_spend_usd >= self.max_budget_usd:
            raise LLMBudgetExceededError(
                f"Превышен лимит бюджета: ${self.current_spend_usd:.4f} из ${self.max_budget_usd:.2f}"
            )

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        rates = self.PRICING_PER_1M.get(model, {"input": 2.00, "output": 8.00})
        cost = (input_tokens / 1_000_000) * rates["input"] + (
            output_tokens / 1_000_000
        ) * rates["output"]
        self.current_spend_usd += cost
        self.total_requests += 1
        logger.info(
            f"[Расход] Модель: {model} | Вход: {input_tokens} | Выход: {output_tokens} "
            f"(Рассуждения: {reasoning_tokens}) | Запрос: ${cost:.6f} | Всего: ${self.current_spend_usd:.5f}"
        )
        return cost


# --- 3. КЛИЕНТ ПОВЕРХ ОФИЦИАЛЬНОГО SDK ---
class ProductionLLMClient:
    def __init__(self, api_key: str, cost_tracker: CostTracker, timeout_sec: float = 20.0):
        # Отключаем скрытые повторы внутри SDK, чтобы явно управлять ими через tenacity
        self.client = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=timeout_sec)
        self.cost_tracker = cost_tracker

    # Повторяем запрос ТОЛЬКО при сетевых сбоях, превышении времени ожидания, кодах 429 и 5xx.
    # Ошибки 400 (неверный запрос) или 401 (ошибка ключа) прерывают выполнение сразу!
    @retry(
        retry=retry_if_exception_type(
            (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
        ),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(3),
        before_sleep=lambda retry_state: logger.warning(
            f"Временный сбой API. Повторная попытка №{retry_state.attempt_number}..."
        ),
    )
    async def generate_structured(
        self,
        system_prompt: str,
        user_input: str,
        response_schema: Type[T],
        model: str = "gpt-4.1-mini",
        max_output_tokens: int = 1000,
        reasoning_effort: Literal["low", "medium", "high"] | None = None,
    ) -> T:
        # 1. Проверяем остаток бюджета до отправки сетевого запроса
        self.cost_tracker.check_budget()

        kwargs = {
            "model": model,
            "instructions": system_prompt,
            "input": user_input,
            "text_format": response_schema,
            "max_output_tokens": max_output_tokens,
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}

        # Используем актуальный метод responses.parse
        # Для сторонних совместимых серверов (vLLM / OpenRouter) используйте:
        # self.client.chat.completions.parse(..., response_format=response_schema)
        response = await self.client.responses.parse(**kwargs)

        # 2. Записываем статистику расхода токенов
        if response.usage:
            reasoning_tokens = getattr(
                response.usage.output_tokens_details, "reasoning_tokens", 0
            )
            self.cost_tracker.record_usage(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                reasoning_tokens=reasoning_tokens,
            )

        # 3. Защита от обрыва JSON при нехватке лимита токенов
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", "unknown")
            raise LLMOutputTruncatedError(
                f"Генерация оборвалась (причина: {reason}). Лимит: {max_output_tokens} токенов."
            )

        # 4. Защита от отказа модели и пустого ответа
        if response.output_parsed is None:
            raise LLMRefusalError(
                f"Модель отказалась формировать ответ по схеме. Текст: {response.output_text}"
            )

        return response.output_parsed


# --- 4. ПРИМЕР РАЗДЕЛЕНИЯ ОТВЕТСТВЕННОСТИ (МОДЕЛЬ И КОД) ---
class TicketCategory(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    DELIVERY = "delivery"
    OTHER = "other"

class TicketExtractionSchema(BaseModel):
    """Схема для модели: ТОЛЬКО извлечение смысла и сущностей. Никаких расчетов!"""
    category: TicketCategory
    is_urgent_tone: bool = Field(description="Есть ли в тексте прямая агрессия или угроза судом")
    mentioned_order_ids: list[str] = Field(description="Список упомянутых номеров заказов")
    summary_ru: str = Field(description="Краткая суть обращения в одно предложение")

def calculate_priority_and_sla_hours(
    extracted: TicketExtractionSchema, customer_total_spend_usd: float
) -> dict:
    """Строгая логика на Python (100% предсказуемость)."""
    if extracted.category == TicketCategory.BILLING and customer_total_spend_usd >= 1000:
        sla_hours = 1
        priority = "CRITICAL"
    elif extracted.is_urgent_tone:
        sla_hours = 4
        priority = "HIGH"
    else:
        sla_hours = 24
        priority = "NORMAL"

    return {
        "priority": priority,
        "sla_hours": sla_hours,
        "orders_to_check": extracted.mentioned_order_ids,
        "summary": extracted.summary_ru,
    }