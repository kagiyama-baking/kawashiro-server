"""HNAgentConfig に front_page_limit フィールドを追加."""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hn_agent", "0013_make_prompt_refs_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="hnagentconfig",
            name="front_page_limit",
            field=models.IntegerField(
                default=30,
                help_text=(
                    "HNフロントページから1回のポーリングで取得するストーリー件数。"
                    "HN Web UI のトップは30件ですが、Algolia API 経由で最大1000件程度まで取得可能。"
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="フロントページ取得件数",
            ),
        ),
    ]
