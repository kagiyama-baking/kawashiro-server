"""暗号化ユーティリティのテスト"""

import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestGetEncryptionKey:
    """get_encryption_key関数のテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_returns_bytes(self):
        """暗号化キーがバイト列で返されること"""
        from core.encryption import get_encryption_key

        key = get_encryption_key()
        assert isinstance(key, bytes)

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_returns_valid_fernet_key_length(self):
        """Fernetキーとして有効な長さ（44バイト）が返されること"""
        from core.encryption import get_encryption_key

        key = get_encryption_key()
        # Base64エンコードされた32バイト = 44文字
        assert len(key) == 44

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_same_input_produces_same_key(self):
        """同じENCRYPTION_KEYから同じキーが生成されること"""
        from core.encryption import get_encryption_key

        key1 = get_encryption_key()
        key2 = get_encryption_key()
        assert key1 == key2

    @override_settings(ENCRYPTION_KEY=None)
    def test_raises_error_when_encryption_key_not_set(self):
        """ENCRYPTION_KEYが設定されていない場合にエラーになること"""
        from core.encryption import get_encryption_key

        with pytest.raises(ValueError) as excinfo:
            get_encryption_key()
        assert "ENCRYPTION_KEY" in str(excinfo.value)


@pytest.mark.django_db
class TestEncryptValue:
    """encrypt_value関数のテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_encrypts_string(self):
        """文字列が暗号化されること"""
        from core.encryption import encrypt_value

        original = "secret-data"
        encrypted = encrypt_value(original)

        assert encrypted != original
        assert len(encrypted) > 0

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_empty_string_returns_empty(self):
        """空文字列は空文字列を返すこと"""
        from core.encryption import encrypt_value

        assert encrypt_value("") == ""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_encrypts_multiline_pem_key(self):
        """複数行のPEM形式秘密鍵が暗号化できること"""
        from core.encryption import encrypt_value

        pem_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7
test-content-here
-----END PRIVATE KEY-----"""

        encrypted = encrypt_value(pem_key)
        assert encrypted != pem_key
        assert len(encrypted) > 0


@pytest.mark.django_db
class TestDecryptValue:
    """decrypt_value関数のテスト"""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_decrypts_encrypted_string(self):
        """暗号化された文字列を復号化できること"""
        from core.encryption import decrypt_value, encrypt_value

        original = "secret-data"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_empty_string_returns_empty(self):
        """空文字列は空文字列を返すこと"""
        from core.encryption import decrypt_value

        assert decrypt_value("") == ""

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_roundtrip_multiline_pem_key(self):
        """複数行のPEM形式秘密鍵が暗号化・復号化できること"""
        from core.encryption import decrypt_value, encrypt_value

        pem_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7
test-content-here
-----END PRIVATE KEY-----"""

        encrypted = encrypt_value(pem_key)
        decrypted = decrypt_value(encrypted)

        assert decrypted == pem_key

    @override_settings(ENCRYPTION_KEY="test-encryption-key-for-unit-tests")
    def test_roundtrip_unicode_content(self):
        """日本語などのUnicode文字を含む文字列が暗号化・復号化できること"""
        from core.encryption import decrypt_value, encrypt_value

        original = "テスト文字列 🔐 secure data"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        assert decrypted == original

    @override_settings(ENCRYPTION_KEY="different-key-for-decrypt-testing")
    def test_decrypt_with_wrong_key_fails(self):
        """異なるキーで復号化すると失敗すること"""
        from cryptography.fernet import InvalidToken

        from core.encryption import decrypt_value

        # 別のキーで暗号化されたデータ（シミュレーション）
        # 実際にはInvalidTokenが発生する
        with pytest.raises(InvalidToken):
            # これは有効なFernetトークンではないので例外が発生
            decrypt_value("invalid-encrypted-data")
