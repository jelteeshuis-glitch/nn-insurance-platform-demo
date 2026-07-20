"""
Field-Level Encryption — PII Protection at Rest (ADR-005)

Provides a small abstraction for encrypting/decrypting sensitive fields
(BSN, IBAN, email, address). The demo uses Fernet (AES-128-CBC + HMAC) with a
key supplied at construction time — in production the key comes from Azure Key
Vault, never from source code (contrast the hardcoded ``ENCRYPTION_KEY`` in
``legacy/src/utils.py``).
"""
from abc import ABC, abstractmethod

from cryptography.fernet import Fernet


class EncryptionService(ABC):
    """Abstract symmetric field encryptor."""

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return an opaque ciphertext token for ``plaintext``."""

    @abstractmethod
    def decrypt(self, token: str) -> str:
        """Recover the plaintext from an encryption token."""


class FernetEncryptionService(EncryptionService):
    """Fernet-backed encryptor. Key is injected, never hardcoded."""

    def __init__(self, key: bytes | str | None = None):
        if key is None:
            key = Fernet.generate_key()
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
