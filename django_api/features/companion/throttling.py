"""Companion の実行（`/companion/run/`）の回数制限."""

from rest_framework.throttling import UserRateThrottle

from .models import CompanionConfig


class CompanionRateThrottle(UserRateThrottle):
    """有効な Companion 設定の上限（1 分あたり）で、ユーザーごとに数える.

    記録のキーは `UserRateThrottle` のまま（認証済みならユーザーの pk）。上限は毎回
    DB から読むので、admin で変えると次のリクエストから効く。そのため DRF の
    `ScopedRateThrottle` と同じく、`__init__` ではなく `allow_request` でレートを
    決める。有効な設定がないときは数えない（ビューが 503 を返す）。
    """

    scope = "companion_run"

    def __init__(self) -> None:
        # SimpleRateThrottle.__init__ は scope の既定レートを探すので呼ばない
        pass

    def allow_request(self, request, view) -> bool:
        limit = (
            CompanionConfig.objects.filter(is_active=True)
            .values_list("rate_limit", flat=True)
            .first()
        )
        if limit is None:
            return True
        self.rate = f"{limit}/minute"
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

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
