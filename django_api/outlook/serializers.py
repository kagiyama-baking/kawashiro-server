"""Outlookアプリケーションのシリアライザー"""

from datetime import date, timedelta

from rest_framework import serializers


class EventsQuerySerializer(serializers.Serializer):
    """予定一覧取得用のクエリパラメータシリアライザー"""

    start_date = serializers.DateField(
        required=False,
        help_text="取得開始日（YYYY-MM-DD形式、デフォルト: 今日）",
    )
    end_date = serializers.DateField(
        required=False,
        help_text="取得終了日（YYYY-MM-DD形式、daysと同時指定時はend_dateが優先）",
    )
    days = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=365,
        help_text="取得日数（1-365、デフォルト: 1、end_dateが指定されていない場合に使用）",
    )

    def validate_days(self, value):
        """daysの値を検証"""
        if value is not None and value < 1:
            raise serializers.ValidationError("daysは1以上を指定してください")
        return value

    def validate(self, attrs):
        """日付の組み合わせを検証"""
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        days = attrs.get("days")

        # start_dateのデフォルト値（今日）
        if start_date is None:
            start_date = date.today()
            attrs["start_date"] = start_date

        # end_dateとdaysの処理
        if end_date is not None:
            # end_dateが指定されている場合はそれを使用
            if end_date < start_date:
                raise serializers.ValidationError(
                    {"end_date": "end_dateはstart_date以降を指定してください"}
                )
        else:
            # end_dateが指定されていない場合はdaysを使用
            if days is None:
                days = 1
            end_date = start_date + timedelta(days=days - 1)
            attrs["end_date"] = end_date

        return attrs


class EventInfoSerializer(serializers.Serializer):
    """カレンダーイベント情報のシリアライザー"""

    id = serializers.CharField(read_only=True)
    subject = serializers.CharField(read_only=True)
    start = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    is_all_day = serializers.BooleanField(source="isAllDay", read_only=True)
    organizer = serializers.SerializerMethodField()
    web_link = serializers.CharField(source="webLink", read_only=True)
    body_preview = serializers.CharField(source="bodyPreview", read_only=True)

    def get_start(self, obj):
        """開始日時を取得"""
        start = obj.get("start", {})
        if isinstance(start, dict):
            date_time = start.get("dateTime", "")
            return f"{date_time}+09:00" if date_time else None
        return start

    def get_end(self, obj):
        """終了日時を取得"""
        end = obj.get("end", {})
        if isinstance(end, dict):
            date_time = end.get("dateTime", "")
            return f"{date_time}+09:00" if date_time else None
        return end

    def get_location(self, obj):
        """場所を取得"""
        location = obj.get("location")
        if location is None:
            return None
        if isinstance(location, dict):
            return location.get("displayName", "")
        return location

    def get_organizer(self, obj):
        """主催者を取得"""
        organizer = obj.get("organizer", {})
        if isinstance(organizer, dict):
            email_address = organizer.get("emailAddress", {})
            if isinstance(email_address, dict):
                return email_address.get("address", "")
        return ""
