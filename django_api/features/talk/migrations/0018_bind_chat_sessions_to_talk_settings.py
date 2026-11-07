"""既存のチャットを Talk 設定へ移す（チャットに使われたプリセットごとに 1 件作る）.

0017 までのチャットは、旧プリセット名（`ChatSession.config_name`）で会話生成設定
（`TalkConfig`）に紐づいていた。前進では、Talk 設定のないチャットに使われているプリセット
ごとに、同じシステムプロンプトと音声の Talk 設定（有効・シーンなし）を作り、そのチャットを
紐づける（更新日時は変えない）。名前はプリセットの表示名（空白だけならプリセット名）で、
表示名がほかのプリセットと重なるときは「表示名（プリセット名）」にする。

同じ名前の Talk 設定がすでにあり、システムプロンプトも同じなら、作らずにそれへ紐づける
（音声は違ってもよい。移した後に admin で調整した設定を、紐づけ直しでも使う）。システム
プロンプトが違うか、作る名前どうしが重なるときは、何も変えずに RuntimeError で止める。
プリセットが消えたチャットは紐づけない。旧プリセット名は変えない。

後退では何もしない（0017 を戻すと Talk 設定の表と列ごと消え、旧プリセット名は残っている）。
"""

from collections import Counter

from django.db import migrations

# Talk 設定にプリセットから写す音声の項目（AbstractTTSSettings。migration はモデルのコードに
# 依らないので、ここに持つ）
TTS_FIELDS = (
    "tts_enabled",
    "tts_model",
    "tts_style",
    "tts_style_weight",
    "tts_speed",
    "tts_sdp_ratio",
    "tts_noise_scale",
    "tts_noise_scale_w",
    "tts_format",
)


def _display_name(config) -> str:
    return config.display_name.strip() or config.name


def _planned_names(talk_config, configs) -> dict[str, str]:
    """プリセット名 → 作る Talk 設定の名前（表示名が重なるものは、プリセット名を付ける）."""
    counts = Counter(_display_name(c) for c in talk_config.objects.all())
    return {
        config.name: (
            f"{_display_name(config)}（{config.name}）"
            if counts[_display_name(config)] > 1
            else _display_name(config)
        )
        for config in configs
    }


def _problems(planned, configs, existing) -> list[str]:
    """移せない理由（作る名前どうしの重なりと、同じ名前で別のシステムプロンプトの設定）."""
    problems = []
    for name, count in Counter(planned.values()).items():
        if count > 1:
            presets = sorted(p for p, n in planned.items() if n == name)
            problems.append(
                f"- プリセット {'・'.join(presets)} がどれも「{name}」になります"
            )
    for config in configs:
        setting = existing.get(planned[config.name])
        if (
            setting is not None
            and setting.system_prompt_ref_id != config.system_prompt_ref_id
        ):
            problems.append(
                f"- プリセット {config.name} の「{planned[config.name]}」は、"
                "別のシステムプロンプトの Talk 設定にすでに使われています"
            )
    return problems


def bind_sessions_to_settings(apps, schema_editor):
    """Talk 設定のないチャットを、そのプリセットから作った Talk 設定へ紐づける."""
    chat_session = apps.get_model("talk", "ChatSession")
    talk_config = apps.get_model("talk", "TalkConfig")
    talk_setting = apps.get_model("talk", "TalkSetting")

    unbound = chat_session.objects.filter(setting__isnull=True).exclude(config_name="")
    used = set(unbound.values_list("config_name", flat=True))
    configs = list(talk_config.objects.filter(name__in=used).order_by("name"))
    if not configs:
        return
    planned = _planned_names(talk_config, configs)
    existing = {
        s.name: s for s in talk_setting.objects.filter(name__in=planned.values())
    }
    problems = _problems(planned, configs, existing)
    if problems:
        raise RuntimeError(
            "既存のチャットを Talk 設定へ移せないので、migration を止めました"
            "（何も変えていません）。Talk 設定は、チャットに使われたプリセットの表示名で"
            "作ります。重なる表示名か、同じ名前の Talk 設定の名前を変えてから、"
            "migrate し直してください:\n" + "\n".join(problems)
        )
    for config in configs:
        setting = existing.get(planned[config.name])
        if setting is None:
            setting = talk_setting.objects.create(
                name=planned[config.name],
                is_enabled=True,
                system_prompt_ref_id=config.system_prompt_ref_id,
                **{field: getattr(config, field) for field in TTS_FIELDS},
            )
        unbound.filter(config_name=config.name).update(setting=setting)


class Migration(migrations.Migration):
    dependencies = [
        ("talk", "0017_talksetting_chatsession_setting_skill"),
    ]

    operations = [
        migrations.RunPython(bind_sessions_to_settings, migrations.RunPython.noop),
    ]
