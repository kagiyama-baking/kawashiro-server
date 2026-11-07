"""migration のテストの共通ヘルパ（DB に当たっている時点のモデルを引く）.

migration を行き来するテストの後始末では、作った行を、いま DB に当たっている時点の
モデルで消す（いまのコードのモデルは、戻した後の表や列と合わない）。プロンプトの
モデルと、設定がシステムプロンプトを持つ項目の名前は、時点によって違う。
"""

from django.db.migrations.executor import MigrationExecutor


def applied_apps(executor: MigrationExecutor):
    """DB に当たっている migration の時点のモデルを引ける apps を返す（グラフを読み直す）."""
    executor.loader.build_graph()
    nodes = executor.loader.graph.nodes
    applied = [key for key in executor.loader.applied_migrations if key in nodes]
    return executor.loader.project_state(applied).apps


def prompt_model(apps):
    """その時点のプロンプトのモデルを返す.

    llm_config の 0018 の後は llm_config の Prompt、その前は langfuse_integration の
    LangfusePromptRef。移している途中（langfuse_integration の 0004 の前）は両方あり、
    同じ表を使うので、Prompt を返す。
    """
    try:
        return apps.get_model("llm_config", "Prompt")
    except LookupError:
        return apps.get_model("langfuse_integration", "LangfusePromptRef")


def system_prompt_field(model) -> str:
    """設定（CompanionConfig・TalkSetting）がシステムプロンプトを持つ項目の名前.

    companion の 0008・talk の 0020 で system_prompt_ref から system_prompt に改めた。
    """
    names = {field.name for field in model._meta.get_fields()}
    return "system_prompt" if "system_prompt" in names else "system_prompt_ref"
