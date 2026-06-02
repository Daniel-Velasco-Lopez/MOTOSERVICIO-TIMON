import structlog
from typing import Optional
from google.genai import Client as GeminiClient
from google.genai import types

from app.config import settings

logger = structlog.get_logger()


class GeminiService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None

    async def connect(self):
        if not settings.gemini_api_key:
            logger.warning("gemini_api_key_not_set")
            return
        self.client = GeminiClient(api_key=settings.gemini_api_key)
        logger.info("gemini_connected", model=settings.gemini_model)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.8,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[type] = None,
        tools: Optional[list] = None,
    ) -> str:
        if not self.client:
            raise RuntimeError("Gemini no conectado")

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )

        if response_mime_type:
            config.response_mime_type = response_mime_type
        if response_schema:
            config.response_schema = response_schema
        if tools:
            config.tools = tools

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )

        if not response.candidates:
            raise RuntimeError("Gemini: sin candidatos en respuesta")

        return response.text

    async def embed(self, text: str) -> list[float]:
        if not self.client:
            raise RuntimeError("Gemini no conectado")

        response = self.client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.qdrant_vector_size,
            ),
        )

        if not response.embeddings:
            raise RuntimeError("Gemini: sin embeddings en respuesta")

        return response.embeddings[0].values

    async def generate_with_function_call(
        self,
        prompt: str,
        tools: list,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> tuple[str, Optional[list[types.FunctionCall]]]:
        if not self.client:
            raise RuntimeError("Gemini no conectado")

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )

        function_calls = []
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)

        return response.text, function_calls if function_calls else None


gemini_service = GeminiService()
