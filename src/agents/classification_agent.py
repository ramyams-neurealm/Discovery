from __future__ import annotations

import asyncio
import logging
import warnings
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult
from src.prompts.classification_prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
)
from src.tools.classification_policy import (
    normalize_classification,
)


logger = logging.getLogger(__name__)


warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="pydantic",
)


class DataClassificationAgent(BaseAgent):
    def __init__(
        self,
        settings,
        key_vault,
        repository=None,
    ):
        super().__init__(settings, key_vault)

        self.repository = repository

        self._raw_llm = build_llm(
            self.settings,
            self.key_vault,
        )

        self._structured_llm = (
            self._raw_llm.with_structured_output(
                ClassificationResult
            )
        )

        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    CLASSIFICATION_SYSTEM_PROMPT,
                ),
                (
                    "human",
                    "Classify this column context:\n{payload}",
                ),
            ]
        )

        self._chain = self._prompt | self._structured_llm

        self._timeout_seconds = float(
            getattr(
                self.settings,
                "classification_timeout_seconds",
                30,
            )
        )

        configured_concurrency = int(
            getattr(
                self.settings,
                "classification_max_concurrency",
                5,
            )
        )

        self._max_concurrency = max(
            1,
            min(configured_concurrency, 10),
        )

    def classify(
        self,
        column_payload: dict[str, Any],
    ):
        """
        Classify one column synchronously.
        """

        result = self._chain.invoke(
            {
                "payload": column_payload,
            }
        )

        return normalize_classification(
            result,
            column_payload,
            self.settings.classification_confidence_threshold,
        )

    async def aclassify(
        self,
        column_payload: dict[str, Any],
    ):
        """
        Classify one column asynchronously with a timeout.
        """

        try:
            result = await asyncio.wait_for(
                self._chain.ainvoke(
                    {
                        "payload": column_payload,
                    }
                ),
                timeout=self._timeout_seconds,
            )

        except asyncio.TimeoutError:
            logger.warning(
                "Column classification timed out",
                extra={
                    "schema_name": column_payload.get(
                        "schema_name"
                    ),
                    "table_name": column_payload.get(
                        "table_name"
                    ),
                    "column_name": column_payload.get(
                        "column_name"
                    ),
                    "timeout_seconds": (
                        self._timeout_seconds
                    ),
                },
            )

            result = ClassificationResult(
                is_sensitive=False,
                confidence=0.0,
                reason=(
                    "Classification timed out after "
                    f"{self._timeout_seconds} seconds."
                ),
            )

        except Exception as error:
            logger.warning(
                "Column classification failed",
                extra={
                    "schema_name": column_payload.get(
                        "schema_name"
                    ),
                    "table_name": column_payload.get(
                        "table_name"
                    ),
                    "column_name": column_payload.get(
                        "column_name"
                    ),
                    "error_type": (
                        error.__class__.__name__
                    ),
                },
                exc_info=True,
            )

            result = ClassificationResult(
                is_sensitive=False,
                confidence=0.0,
                reason=(
                    "Classification failed: "
                    f"{error.__class__.__name__}"
                ),
            )

        return normalize_classification(
            result,
            column_payload,
            self.settings.classification_confidence_threshold,
        )

    async def batch_classify(
        self,
        column_payloads: list[dict[str, Any]],
        max_concurrency: int | None = None,
    ):
        """
        Classify multiple columns concurrently using bounded
        concurrency.
        """

        if not column_payloads:
            return []

        concurrency = (
            max_concurrency
            if max_concurrency is not None
            else self._max_concurrency
        )

        concurrency = max(
            1,
            min(int(concurrency), 10),
        )

        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_classify(payload):
            async with semaphore:
                return await self.aclassify(payload)

        tasks = [
            asyncio.create_task(
                bounded_classify(payload)
            )
            for payload in column_payloads
        ]

        gathered_results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        classification_results = []

        for payload, result in zip(
            column_payloads,
            gathered_results,
        ):
            if isinstance(result, BaseException):
                logger.warning(
                    "Unexpected batch classification failure",
                    extra={
                        "schema_name": payload.get(
                            "schema_name"
                        ),
                        "table_name": payload.get(
                            "table_name"
                        ),
                        "column_name": payload.get(
                            "column_name"
                        ),
                        "error_type": (
                            result.__class__.__name__
                        ),
                    },
                )

                fallback_result = ClassificationResult(
                    is_sensitive=False,
                    confidence=0.0,
                    reason=(
                        "Batch classification failed: "
                        f"{result.__class__.__name__}"
                    ),
                )

                result = normalize_classification(
                    fallback_result,
                    payload,
                    (
                        self.settings
                        .classification_confidence_threshold
                    ),
                )

            classification_results.append(result)

        return classification_results

    def classify_batch(
        self,
        column_payloads: list[dict[str, Any]],
        max_concurrency: int | None = None,
    ):
        """
        Synchronous wrapper for the synchronous supervisor.
        """

        if not column_payloads:
            return []

        try:
            asyncio.get_running_loop()

        except RuntimeError:
            return asyncio.run(
                self.batch_classify(
                    column_payloads=column_payloads,
                    max_concurrency=max_concurrency,
                )
            )

        raise RuntimeError(
            "classify_batch() cannot run inside an active "
            "event loop. Use batch_classify() instead."
        )