"""サブエージェントの出力スキーマ.

LLM の JSON 応答の検証に使う（スキーマ自体はモデルへ送らない）。必須キーは従来の検査と
同じにし、未知のキーも残す。Reporter は文字列項目の `None` を扱えないので、`null` は
既定値に寄せる。リストの `null` も「情報なし」として受け入れる。
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _default_if_none(default: str) -> BeforeValidator:
    """`None` を既定値に置き換えるバリデータを作る."""
    return BeforeValidator(lambda value: default if value is None else value)


def _empty_list_if_none(value: Any) -> Any:
    """`None` を空リストに置き換える."""
    return [] if value is None else value


_Text = Annotated[str, _default_if_none("")]
_Author = Annotated[str, _default_if_none("Anonymous")]
_TextList = Annotated[list[str], BeforeValidator(_empty_list_if_none)]


class _AnalysisModel(BaseModel):
    """LLM の応答を受ける基底クラス."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)


class CommentHighlight(_AnalysisModel):
    """注目コメント."""

    author: _Author = "Anonymous"
    quote: _Text = ""
    stance: _Text = ""


class DetectiveAnalysis(_AnalysisModel):
    """Detective の分析結果."""

    title_ja: _Text
    comment_highlights: Annotated[
        list[CommentHighlight], BeforeValidator(_empty_list_if_none)
    ]
    why_trending: _Text = ""
    background: _Text = ""
    summary: _Text = ""


class PastCase(_AnalysisModel):
    """過去の類似事例."""

    name: _Text = ""
    lesson: _Text = ""


class CriticalComment(_AnalysisModel):
    """批判的なコメント."""

    author: _Author = "Anonymous"
    quote: _Text = ""
    angle: _Text = ""


class DevilsAdvocateAnalysis(_AnalysisModel):
    """Devil's Advocate の分析結果."""

    concerns: _TextList
    critical_comments: Annotated[
        list[CriticalComment], BeforeValidator(_empty_list_if_none)
    ]
    past_cases: Annotated[list[PastCase], BeforeValidator(_empty_list_if_none)] = Field(
        default_factory=list
    )
    summary: _Text = ""


class OfficialPatch(_AnalysisModel):
    """公式パッチの情報（available と version は Reporter が型によらず扱える）."""

    available: Any = False
    version: Any = None
    url: str | None = None


class SecurityAnalysis(_AnalysisModel):
    """Security Responder の分析結果."""

    severity: Annotated[str, _default_if_none("unknown")]
    summary: _Text
    cve_ids: _TextList = Field(default_factory=list)
    affected: _TextList = Field(default_factory=list)
    workarounds: _TextList = Field(default_factory=list)
    official_patch: OfficialPatch | None = None
