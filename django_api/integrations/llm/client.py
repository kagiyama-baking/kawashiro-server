"""プロバイダー非依存LLMクライアント.

LiteLLM Proxy経由で任意のLLMプロバイダーに接続する。
OpenAI SDKのbase_urlをLiteLLM Proxyに向けることで、
Chat Completions API / Embeddings APIをプロバイダー非依存で使用する。
"""

from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI

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

        Args:
            text: 埋め込み対象のテキスト
            dimensions: 出力次元数（指定するとAPIが切り詰める）

        Returns:
            embeddingベクトル（floatのリスト）

        Raises:
            LLMTimeoutError: タイムアウト時
            LLMClientError: API接続エラー時
        """
        kwargs: dict[str, Any] = {"model": self.model, "input": text}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions

        try:
            response = self._client.embeddings.create(**kwargs)
            return response.data[0].embedding
        except APITimeoutError as e:
            raise LLMTimeoutError(
                "Embedding APIへのリクエストがタイムアウトしました"
            ) from e
        except APIConnectionError as e:
            raise LLMClientError("Embedding APIへの接続に失敗しました") from e
