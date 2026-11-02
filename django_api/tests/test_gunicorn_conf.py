"""本番の gunicorn 設定のテスト."""

import gc
import importlib
import runpy
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from django.conf import settings

CONF_PATH = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
DOCKERFILE_PATH = Path(__file__).resolve().parents[1] / "Dockerfile"


@pytest.fixture
def conf() -> dict:
    """設定ファイルを gunicorn と同じように Python として読む."""
    return runpy.run_path(str(CONF_PATH))


@pytest.mark.unit
class TestGunicornConf:
    """メモリ共有の設定."""

    def test_preload_is_enabled(self, conf):
        """fork の前にアプリを読み込む."""
        assert conf["preload_app"] is True

    def test_when_ready_prepares_shared_memory_before_fork(self, conf):
        """URLconf を読み込み、DB 接続を閉じてから GC を止める."""
        steps = MagicMock()
        # Django の内部からも呼ばれるので、実体を通して順序だけを記録する
        steps.import_module.side_effect = importlib.import_module

        with (
            # when_ready の中で読み込むので、ここで差し替えれば効く
            patch("importlib.import_module", steps.import_module),
            patch("django.db.connections.close_all", steps.close_all),
            patch.object(gc, "collect", steps.collect),
            patch.object(gc, "freeze", steps.freeze),
        ):
            conf["when_ready"](MagicMock())

        order = [
            steps.mock_calls.index(step)
            for step in (
                call.import_module(settings.ROOT_URLCONF),
                call.close_all(),
                call.collect(),
                call.freeze(),
            )
        ]
        assert order == sorted(order)

    def test_config_is_copied_into_image(self):
        """Dockerfile はファイルを列挙してコピーするので、設定ファイルも含める."""
        assert "gunicorn.conf.py" in DOCKERFILE_PATH.read_text()
