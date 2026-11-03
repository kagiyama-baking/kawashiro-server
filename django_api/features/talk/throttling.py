"""会話生成（`/talk/synthesize/`）の回数制限."""

from rest_framework.throttling import SimpleRateThrottle

from .models import TalkConfig
from .serializers import TalkRequestSerializer


class TalkConfigRateThrottle(SimpleRateThrottle):
    """会話生成設定の上限（1 分あたり）で、ユーザーとプリセットの組ごとに数える.

    上限は本文の `config_name` が指すプリセットで決まるので、DRF の
    `ScopedRateThrottle` と同じく `__init__` ではなく `allow_request` でレートを
    決める。上限は毎回 DB から読むので、admin で変えると次のリクエストから効く。
    本文が不正なときや設定がないときは数えない（ビューが 400 / 404 を返す）。
    """

    scope = "talk_synthesize"

    def __init__(self) -> None:
        # SimpleRateThrottle.__init__ は scope の既定レートを探すので呼ばない
        pass

    def allow_request(self, request, view) -> bool:
        target = self._find_config(request)
        if target is None:
            return True
        self.config_pk, limit = target
        self.rate = f"{limit}/minute"
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view) -> str:
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{ident}_{self.config_pk}",
        }

    def wait(self) -> float | None:
        """次の 1 回が通るまでの秒数（Retry-After）.

        admin で上限を下げた直後は、直近 1 分の回数が新しい上限を超えている。
        DRF の既定はこのとき None を返して Retry-After が付かないので、上限の
        位置にある記録が 1 分の窓から抜けるまでの秒数を返す（記録は新しい順）。
        """
        if 0 < self.num_requests <= len(self.history):
            oldest_counted = self.history[self.num_requests - 1]
            return self.duration - (self.now - oldest_counted)
        return super().wait()

    @staticmethod
    def _find_config(request) -> tuple[int, int] | None:
        """ビューと同じ検証で設定名を読み、プリセットの (pk, 上限) を返す.

        検証をそろえないと、ビューは通すのにここでは別の名前に見える値
        （前後に空白を足した名前など）で制限を回避できてしまう。
        """
        serializer = TalkRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return None
        return (
            TalkConfig.objects.filter(name=serializer.validated_data["config_name"])
            .values_list("pk", "synthesize_rate_limit")
            .first()
        )
