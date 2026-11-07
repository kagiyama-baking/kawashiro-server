"""Langfuse のプロンプトの取得とセッションの伝播."""

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from .exceptions import LangfusePromptError

logger = logging.getLogger(__name__)


def fetch_text_prompt(
    name: str, *, label: str, variables: Mapping[str, Any] | None = None
) -> str:
    """Langfuse の Text 型プロンプトを名前とラベルで取り、本文を返す.

    プロジェクトで Langfuse のプロンプトを取る唯一の経路（Prompts のプロンプトは
    `integrations.llm.prompts.resolve_prompt_text`、スキルの本文は
    `integrations.llm.skills.resolve_skill_body` が使う）。フォールバックはなく、取れなければ
    例外にする。`variables` を渡すと、本文の `{{x}}` を SDK の compile で展開する（値は str に
    する。渡していない変数の `{{x}}` は残る）。None（既定）なら展開せず、本文をそのまま返す。

    SDK 自身のプロンプトキャッシュの挙動は変えない。TTL（既定 60 秒）を過ぎた
    ものも返しつつ裏で取り直すので、一度取れた後は取得に失敗しても古い本文が
    返る。例外になるのは、プロセス内のキャッシュにまだ無いとき（初回や、
    Langfuse で見つからなくなってキャッシュから外れた後）だけ。

    Args:
        name: Langfuse 上のプロンプト名
        label: 取得するラベル（production / staging など）
        variables: 本文に差し込む変数（None なら展開しない）

    Returns:
        プロンプト本文（`variables` が None なら未展開）

    Raises:
        LangfusePromptError: langfuse を import できない・Langfuse に届かない・
            未登録・Text 型でないとき。取得の失敗は元の例外を __cause__ に持つ。
    """
    try:
        from langfuse import get_client
        from langfuse.model import TextPromptClient

        prompt = get_client().get_prompt(name, label=label)
    except Exception as exc:
        logger.warning(
            "Langfuseプロンプト取得失敗: %s (label=%s)", name, label, exc_info=True
        )
        raise LangfusePromptError(
            f"Langfuse からプロンプトを取得できませんでした: {name} (label={label})"
        ) from exc

    if not isinstance(prompt, TextPromptClient):
        prompt_type = type(prompt).__name__
        logger.warning(
            "Text 型ではないプロンプトは未対応: %s (label=%s, type=%s)",
            name,
            label,
            prompt_type,
        )
        raise LangfusePromptError(
            f"Text 型ではないプロンプトは使えません: {name} "
            f"(label={label}, type={prompt_type})"
        )

    if variables is None:
        return prompt.prompt
    return prompt.compile(**variables)


@contextmanager
def langfuse_session(session_id: str | None) -> Iterator[None]:
    """中で実行する処理のトレースと配下の観測に、Langfuse のセッション ID を伝播する.

    Langfuse の Sessions (https://langfuse.com/docs/observability/features/sessions)
    で、同じセッションのトレースをまとめて表示するためのもの。SDK 4 系では属性の
    伝播が with 文（`propagate_attributes`）になったので、本処理をこの中で実行する。
    伝播は、入った時点の現在のスパン（`@observe` の関数の中ならそのスパン）と、
    中で始まるスパンに付く。

    `session_id` が None か空文字なら何もしない。伝播の開始・解除に失敗しても
    warning ログを出すだけで、本処理は続ける（本処理の例外はそのまま送出する）。

    Args:
        session_id: Langfuse のセッション ID（例: チャットセッションの UUID）
    """
    context = None
    if session_id:
        try:
            from langfuse import propagate_attributes

            context = propagate_attributes(session_id=str(session_id))
            context.__enter__()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse session_id 設定失敗: %s", exc)
            context = None
    try:
        yield
    finally:
        if context is not None:
            try:
                context.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Langfuse session_id 解除失敗: %s", exc)
