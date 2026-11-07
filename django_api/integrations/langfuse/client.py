"""Langfuseプロンプト解決ユーティリティとセッションの伝播."""

import logging
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from .exceptions import LangfusePromptError, PromptUnavailableError

if TYPE_CHECKING:
    from .models import LangfusePromptRef

logger = logging.getLogger(__name__)

_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def get_prompt_with_variables(
    ref: "LangfusePromptRef",
) -> tuple[Callable[..., str], set[str]]:
    """LangfusePromptRef から compile 関数と変数集合を返す.

    1. Langfuse から取得できた場合: prompt.variables と prompt.compile を返す。
    2. 取得失敗時: fallback_text から正規表現で変数を抽出し、
       render_template による簡易 compile 関数を返す。

    Args:
        ref: プロンプト参照

    Returns:
        (compile_fn, variables): compile_fn(**kwargs) でテキスト展開、
        variables は検出された変数名の集合
    """
    try:
        from langfuse import get_client
        from langfuse.model import TextPromptClient

        client = get_client()
        prompt = client.get_prompt(ref.langfuse_prompt_name, label=ref.label)
        if not isinstance(prompt, TextPromptClient):
            logger.warning(
                "Chat 型プロンプトは未対応のため fallback 使用: %s (type=%s)",
                ref.name,
                type(prompt).__name__,
            )
            raise TypeError("ChatPromptClient is not supported")
        variables = set(prompt.variables)
        logger.debug("Langfuseプロンプト取得成功: %s vars=%s", ref.name, variables)
        return prompt.compile, variables
    except ImportError:
        logger.debug("langfuse 未インストール、fallback使用: %s", ref.name)
    except Exception:
        logger.warning(
            "Langfuseプロンプト取得失敗、fallback使用: %s",
            ref.name,
            exc_info=True,
        )

    fallback_text = ref.fallback_text
    variables = set(_VARIABLE_PATTERN.findall(fallback_text))

    def compile_fn(**kwargs: Any) -> str:
        return render_template(fallback_text, kwargs)

    return compile_fn, variables


def resolve_prompt(ref: "LangfusePromptRef", **variables: Any) -> str:
    """LangfusePromptRef からプロンプト文字列を解決する.

    内部で get_prompt_with_variables を使用し、compile 関数を呼び出す。

    Args:
        ref: プロンプト参照
        **variables: テンプレート変数（値は str() 可能であること）

    Returns:
        解決済みプロンプト文字列
    """
    compile_fn, _ = get_prompt_with_variables(ref)
    return compile_fn(**variables)


def resolve_required_prompt(ref: "LangfusePromptRef") -> str:
    """プロンプト（システムプロンプト）の本文を参照から解決し、空なら例外にする.

    `resolve_prompt` は Langfuse から取れなくても例外を出さずにフォールバックテキストへ落ち、
    フォールバックテキストは空でもよい。空のまま「読めた体」で続けないよう、ここで止める。
    変数は展開しない。Langfuse と通信する同期関数なので、イベントループの外で呼ぶ。

    Args:
        ref: プロンプトの参照（変数のない text プロンプト）

    Returns:
        前後の空白を除いた本文

    Raises:
        PromptUnavailableError: 本文が空（空白だけ）の場合
    """
    text = resolve_prompt(ref).strip()
    if not text:
        raise PromptUnavailableError(ref.name)
    return text


def fetch_text_prompt(
    name: str, *, label: str, variables: Mapping[str, Any] | None = None
) -> str:
    """Langfuse の Text 型プロンプトを名前とラベルで取り、本文を返す.

    fallback を持たない取得経路（いまはスキルが使い、いずれプロジェクト全体を
    こちらへ寄せる）。取れなければ fallback_text に落とさず例外にする。
    `variables` を渡すと、本文の `{{x}}` を SDK の compile で展開する（値は str に
    する。渡していない変数の `{{x}}` は残る）。None（既定）なら展開せず、本文を
    そのまま返す。

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


def render_template(template: str, variables: dict[str, Any]) -> str:
    """テンプレート文字列に variables を簡易置換する.

    `{{key}}` を variables[key] で str 置換する Mustache 風簡易レンダラ。
    未知のキーは元の `{{key}}` のまま残す。
    """
    if not variables:
        return template

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _VARIABLE_PATTERN.sub(_replace, template)
