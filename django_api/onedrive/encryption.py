"""暗号化・復号化ユーティリティ

データベースに保存する機密情報の暗号化にFernetを使用します。
"""

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def get_encryption_key() -> bytes:
    """
    ENCRYPTION_KEYからFernet暗号化キーを派生させる

    Fernetキーは32バイトのbase64エンコード文字列である必要があるため、
    ENCRYPTION_KEYをSHA256でハッシュ化してから使用する

    Returns:
        bytes: Fernet暗号化に使用できるキー

    Raises:
        ValueError: ENCRYPTION_KEYが設定されていない場合
    """
    encryption_key = getattr(settings, "ENCRYPTION_KEY", None)
    if not encryption_key:
        raise ValueError(
            "ENCRYPTION_KEY環境変数が設定されていません。\n"
            ".envファイルにENCRYPTION_KEYを追加してください。"
        )
    if len(encryption_key) < 32:
        raise ValueError(
            "ENCRYPTION_KEYは32文字以上である必要があります。\n"
            "十分にランダムな文字列を設定してください。"
        )

    # ENCRYPTION_KEYをバイト列に変換
    key_bytes = encryption_key.encode("utf-8")
    # SHA256でハッシュ化（32バイト出力）
    digest = hashlib.sha256(key_bytes).digest()
    # Base64エンコードしてFernetキーを生成
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plaintext: str) -> str:
    """
    文字列を暗号化する

    Args:
        plaintext: 暗号化する文字列

    Returns:
        str: Base64エンコードされた暗号化文字列。空文字列の場合は空文字列を返す
    """
    if not plaintext:
        return ""

    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """
    暗号化された文字列を復号化する

    Args:
        ciphertext: 復号化する暗号化文字列

    Returns:
        str: 復号化された平文。空文字列の場合は空文字列を返す

    Raises:
        cryptography.fernet.InvalidToken: 復号化に失敗した場合
    """
    if not ciphertext:
        return ""

    key = get_encryption_key()
    f = Fernet(key)
    decrypted = f.decrypt(ciphertext.encode("utf-8"))
    return decrypted.decode("utf-8")
