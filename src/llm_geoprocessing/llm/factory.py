from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel

from llm_geoprocessing.domain.config import Settings
from llm_geoprocessing.domain.errors import ErrorCode, GeoLLMError


class ChatModel(Protocol):
    def invoke(self, messages: list[dict[str, str]]) -> Any:
        raise NotImplementedError


class MockChatModel:
    def invoke(self, messages: list[dict[str, str]]) -> str:
        # Deterministic fallback for smoke tests and local Docker startup.
        user_text = "\n".join(message.get("content", "") for message in messages if message.get("role") == "user")
        if "ndvi" in user_text.lower():
            bbox = self._extract_bbox(user_text) or [-58.6, -34.7, -58.3, -34.5]
            dates = self._extract_dates(user_text) or ("2024-01-01", "2024-01-31")
            return (
                '{"schema_version":"v1","products":[{"id":"A","name":"COPERNICUS/S2_SR_HARMONIZED",'
                f'"date":{{"initial_date":"{dates[0]}","end_date":"{dates[1]}"}},"proj":"default","res":"default"}}],'
                '"actions":[{"geoprocess_name":"index_composite","input_json":{"product_id":"A",'
                f'"bbox":{bbox},"date_initial":"{dates[0]}","date_end":"{dates[1]}",'
                '"bands":["B8","B4"],"reducer":"median","max_tiles":4},"output_id":"ndvi_result"}],'
                '"other_params":{},"assumptions":["Mock planner defaulted to Sentinel-2 NDVI for local smoke test."]}'
            )
        return '{"schema_version":"v1","products":[],"actions":[],"other_params":{},"assumptions":[]}'

    @staticmethod
    def _extract_bbox(text: str) -> list[float] | None:
        match = re.search(r"bbox\s*\[([^\]]+)\]", text, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            values = [float(part.strip()) for part in match.group(1).split(",")]
        except ValueError:
            return None
        return values if len(values) == 4 else None

    @staticmethod
    def _extract_dates(text: str) -> tuple[str, str] | None:
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        if len(dates) >= 2:
            return dates[0], dates[1]
        return None


class LLMFactory(BaseModel):
    settings: Settings

    class Config:
        arbitrary_types_allowed = True

    def create_chat_model(self) -> ChatModel:
        provider = self.settings.geo_llm_provider
        model = self.settings.geo_llm_model

        if provider == "mock":
            return MockChatModel()
        if provider in {"openai", "chatgpt"}:
            if not self.settings.openai_api_key:
                raise GeoLLMError(ErrorCode.CONFIGURATION_ERROR, "OPENAI_API_KEY is required")
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model, api_key=self.settings.openai_api_key.get_secret_value())
        if provider == "gemini":
            if not self.settings.gemini_api_key:
                raise GeoLLMError(ErrorCode.CONFIGURATION_ERROR, "GEMINI_API_KEY is required")
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=self.settings.gemini_api_key.get_secret_value(),
                temperature=0,
            )
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(model=self.settings.ollama_model, base_url=self.settings.ollama_base_url)
        raise GeoLLMError(ErrorCode.CONFIGURATION_ERROR, f"Unsupported provider: {provider}")
