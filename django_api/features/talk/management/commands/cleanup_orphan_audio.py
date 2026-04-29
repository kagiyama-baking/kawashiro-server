"""DB 上 audio_file パスは残るが実体ファイルが無い ChatMessage を整理する."""

from django.core.management.base import BaseCommand

from features.talk.models import ChatMessage


class Command(BaseCommand):
    help = (
        "ChatMessage.audio_file が指す実体ファイルが存在しないレコードを検出し、"
        "audio_file / audio_format / audio_size_bytes をクリアする"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="DB を更新せず、対象件数とパスのみ表示する",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        qs = ChatMessage.objects.exclude(audio_file="")
        orphans: list[ChatMessage] = []
        for msg in qs.iterator():
            name = msg.audio_file.name
            try:
                exists = bool(name) and msg.audio_file.storage.exists(name)
            except (ValueError, NotImplementedError):
                exists = False
            if not exists:
                orphans.append(msg)

        if not orphans:
            self.stdout.write("孤児となった音声レコードはありません。")
            return

        if dry_run:
            self.stdout.write(
                f"[dry-run] {len(orphans)} 件の孤児レコードをクリア対象として検出"
            )
            for msg in orphans:
                self.stdout.write(
                    f"  - id={msg.id} session={msg.session_id} "
                    f"path={msg.audio_file.name}"
                )
            return

        for msg in orphans:
            msg.audio_file = None
            msg.audio_format = ""
            msg.audio_size_bytes = 0
            msg.save(update_fields=["audio_file", "audio_format", "audio_size_bytes"])
        self.stdout.write(f"{len(orphans)} 件の孤児レコードをクリアしました。")
