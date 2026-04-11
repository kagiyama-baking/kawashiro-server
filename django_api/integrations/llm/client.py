"""プロバイダー非依存LLMクライアント.

LiteLLM Proxy経由で任意のLLMプロバイダーに接続する。
OpenAI SDKのbase_urlをLiteLLM Proxyに向けることで、
Chat Completions API / Embeddings APIをプロバイダー非依存で使用する。
"""

from typing import Any

import httpx
from langfuse.openai import OpenAI
from openai import APIConnectionError, APITimeoutError

from .config import get_llm_settings
from .exceptions import LLMClientError, LLMTimeoutError


class LLMClient:
    """LiteLLM Proxy経由のプロバイダー非依存LLMクライアント."""

    def __init__(self, service_name: str):
        """サービス名で初期化.

        Args:
            service_name: サービス識別名（orchestrator, detective, talk, embedding）

        Raises:
            LLMConfigurationError: 設定が存在しない場合
        """
        settings = get_llm_settings(service_name)

        self.model = settings.model_alias
        self.timeout = settings.timeout
        self._service_name = settings.service_name
        self._environment = settings.environment

        self._client = OpenAI(
            base_url=settings.proxy_base_url,
            api_key=settings.proxy_api_key,
            timeout=settings.timeout,
        )

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Chat Completions API呼び出し（Function Calling対応）.

        Args:
            messages: メッセージリスト
            tools: ツール定義リスト（Chat Completions形式）
            tool_choice: ツール選択モード（"auto", "none", "required"）
            **kwargs: 追加パラメータ

        Returns:
            Chat Completionsレスポンスオブジェクト

        Raises:
            LLMTimeoutError: タイムアウト時
            LLMClientError: API接続エラー時
        """
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "extra_body": {
                "metadata": {
                    "service_name": self._service_name,
                    "environment": self._environment,
                }
            },
            "name": f"llm/{self._service_name}",
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice or "auto"
        params.update(kwargs)

        try:
            return self._client.chat.completions.create(**params)
        except APITimeoutError as e:
            raise LLMTimeoutError("LLM APIへのリクエストがタイムアウトしました") from e
        except APIConnectionError as e:
            raise LLMClientError("LLM APIへの接続に失敗しました") from e

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """シンプルなテキスト生成.

        OpenAIClient.generate_text()と同じシグネチャを維持する後方互換メソッド。

        Args:
            prompt: ユーザーメッセージ
            system_prompt: システムプロンプト（オプション）

        Returns:
            生成されたテキスト

        Raises:
            LLMTimeoutError: タイムアウト時
            LLMClientError: API接続エラー時
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.chat_completion(messages)
        return response.choices[0].message.content or ""

    def generate_embedding(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """テキストからembeddingベクトルを生成.

        OpenAI SDK v2.xがvector_store_ids等の余分なパラメータを自動付与し
        Bedrock等のプロバイダーが拒否するため、httpxで直接リクエストする。

        Args:
            text: 埋め込み対象のテキスト
            dimensions: 出力次元数（指定するとAPIが切り詰める）

        Returns:
            embeddingベクトル（floatのリスト）

        Raises:
            LLMTimeoutError: タイムアウト時
            LLMClientError: API接続エラー時
        """
        body: dict[str, Any] = {"model": self.model, "input": text}
        if dimensions is not None:
            body["dimensions"] = dimensions

        try:
            response = httpx.post(
                f"{self._client.base_url}embeddings",
                headers={
                    "Authorization": f"Bearer {self._client.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                "Embedding APIへのリクエストがタイムアウトしました"
            ) from e
        except httpx.HTTPError as e:
            raise LLMClientError("Embedding APIへの接続に失敗しました") from e
