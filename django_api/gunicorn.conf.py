"""本番の gunicorn 設定（作業ディレクトリの gunicorn.conf.py を自動で読む）.

ワーカー数やタイムアウトは起動コマンド側で指定する。ここには、読み込み済みのメモリを
ワーカー間で共有する設定だけを置く。ワーカーごとに import すると 4 ワーカーで 500MiB を超え、
本番の `mem_limit`（512m）に達する。fork の前に読み込めば 200MiB 程度に収まる。
"""

import gc

preload_app = True


def when_ready(server) -> None:
    """fork の直前に、ワーカーで共有するものを揃える."""
    from importlib import import_module

    from django.conf import settings
    from django.db import connections

    # URLconf は最初のリクエストで読まれるので、ここで読まないと各ワーカーの負担になる
    import_module(settings.ROOT_URLCONF)
    # DB 接続のソケットをワーカーへ引き継がない（プロセス間で共有すると壊れる）
    connections.close_all()
    # fork 後の GC が共有ページへ書き込み、コピーが発生するのを防ぐ
    gc.collect()
    gc.freeze()
