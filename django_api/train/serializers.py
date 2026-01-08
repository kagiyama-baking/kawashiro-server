"""Serializers for train diainfo API."""

from rest_framework import serializers


class DiainfoRequestSerializer(serializers.Serializer):
    """運行情報リクエストのシリアライザ"""

    rail_ids = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="路線ID（複数の場合はカンマ区切り）",
    )

    def validate_rail_ids(self, value: str) -> list[str]:
        """rail_idsをリストに変換し、バリデーションする"""
        if not value or not value.strip():
            raise serializers.ValidationError("路線IDを指定してください")

        rail_ids = [rid.strip() for rid in value.split(",") if rid.strip()]

        if not rail_ids:
            raise serializers.ValidationError("路線IDを指定してください")

        if len(rail_ids) > 10:
            raise serializers.ValidationError("路線IDは10個以下で指定してください")

        # セキュリティ: rail_idは数値のみ許可（URLインジェクション防止）
        for rail_id in rail_ids:
            if not rail_id.isdigit():
                raise serializers.ValidationError(
                    f"路線IDは数値で指定してください: {rail_id}"
                )

        return rail_ids


class DiainfoResponseSerializer(serializers.Serializer):
    """運行情報レスポンスのシリアライザ"""

    rail_id = serializers.CharField(help_text="路線ID")
    rail_name = serializers.CharField(allow_null=True, help_text="路線名")
    company_name = serializers.CharField(allow_null=True, help_text="運営会社名")
    status = serializers.CharField(allow_null=True, help_text="運行状況")
    is_delayed = serializers.BooleanField(allow_null=True, help_text="遅延有無")
    message = serializers.CharField(allow_null=True, help_text="詳細メッセージ")
    cause = serializers.CharField(allow_null=True, help_text="遅延原因")
    update_time = serializers.CharField(allow_null=True, help_text="更新日時")
    error = serializers.CharField(allow_null=True, help_text="エラーメッセージ")
