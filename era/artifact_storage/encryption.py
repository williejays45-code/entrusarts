"""AES-256-GCM envelope adapter with external key-authority custody."""

from __future__ import annotations

import os
from typing import Protocol

from .errors import ArtifactStorageError
from .models import EncryptedEnvelope


class ExternalKeyAuthority(Protocol):
    key_authority_id: str

    def generate_data_key(self) -> tuple[bytes, bytes]: ...
    def unwrap_data_key(self, wrapped_data_key: bytes) -> bytes: ...


class Aes256GcmEnvelopeCipher:
    """Uses ``cryptography`` when deployed; keys remain owned by the injected KMS/HSM port."""

    algorithm = "AES-256-GCM"

    def __init__(self, key_authority: ExternalKeyAuthority):
        self.key_authority = key_authority
        self.key_authority_id = key_authority.key_authority_id

    @staticmethod
    def _aesgcm():
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise ArtifactStorageError("ENCRYPTION_UNAVAILABLE") from exc
        return AESGCM

    def encrypt(self, plaintext: bytes, authenticated_metadata: bytes) -> EncryptedEnvelope:
        data_key, wrapped_data_key = self.key_authority.generate_data_key()
        if len(data_key) != 32:
            raise ArtifactStorageError("KEY_AUTHORITY_INVALID")
        nonce = os.urandom(12)
        ciphertext = self._aesgcm()(data_key).encrypt(nonce, plaintext, authenticated_metadata)
        return EncryptedEnvelope(
            self.algorithm, nonce, ciphertext, wrapped_data_key, self.key_authority_id,
        )

    def decrypt(self, envelope: EncryptedEnvelope, authenticated_metadata: bytes) -> bytes:
        if envelope.algorithm != self.algorithm or envelope.key_authority_id != self.key_authority_id:
            raise ArtifactStorageError("CORRUPT")
        data_key = self.key_authority.unwrap_data_key(envelope.wrapped_data_key)
        if len(data_key) != 32:
            raise ArtifactStorageError("CORRUPT")
        try:
            return self._aesgcm()(data_key).decrypt(
                envelope.nonce, envelope.ciphertext, authenticated_metadata,
            )
        except Exception as exc:
            raise ArtifactStorageError("CORRUPT") from exc

