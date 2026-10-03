import socket
import struct
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import anyio


class AttachmentValidationError(ValueError):
    pass


class AttachmentScanError(RuntimeError):
    pass


class AttachmentMalwareDetected(AttachmentScanError):
    pass


class AttachmentScanner(Protocol):
    async def scan(self, data: bytes) -> None: ...


class ClamAVScanner:
    """ClamAV INSTREAM client; any scanner/protocol failure is fail-closed."""

    def __init__(self, host: str, port: int = 3310, timeout: int = 5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    async def scan(self, data: bytes) -> None:
        await anyio.to_thread.run_sync(self._scan, data)

    def _scan(self, data: bytes) -> None:
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as connection:
                connection.settimeout(self.timeout)
                connection.sendall(b"zINSTREAM\0")
                for start in range(0, len(data), 64 * 1024):
                    chunk = data[start : start + 64 * 1024]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096).decode("utf-8", errors="replace").strip("\0\r\n")
        except OSError as exc:
            raise AttachmentScanError("Attachment malware scanner is unavailable") from exc
        if response.endswith("FOUND"):
            raise AttachmentMalwareDetected("Attachment was rejected by malware scanning")
        if not response.endswith("OK"):
            raise AttachmentScanError("Attachment malware scan did not complete safely")


ALLOWED_TYPES: dict[str, frozenset[str]] = {
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/gif": frozenset({".gif"}),
    "application/pdf": frozenset({".pdf"}),
    "application/json": frozenset({".json"}),
    "text/csv": frozenset({".csv"}),
    "text/markdown": frozenset({".md"}),
    "text/plain": frozenset({".txt", ".log"}),
}


def validate_attachment(filename: str, content_type: str, data: bytes, max_bytes: int) -> str:
    clean_name = Path(filename).name.strip()
    if not clean_name or clean_name in {".", ".."} or len(clean_name) > 255:
        raise AttachmentValidationError("Filename is invalid")
    if not data:
        raise AttachmentValidationError("Attachment cannot be empty")
    if len(data) > max_bytes:
        raise AttachmentValidationError("Attachment exceeds the configured size limit")
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    extension = Path(clean_name).suffix.lower()
    if normalized_type not in ALLOWED_TYPES or extension not in ALLOWED_TYPES[normalized_type]:
        raise AttachmentValidationError("File type and extension are not allowed")
    valid_signature = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
        "application/pdf": data.startswith(b"%PDF-"),
    }
    if normalized_type in {"application/json", "text/csv", "text/markdown", "text/plain"}:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AttachmentValidationError("Text attachments must be valid UTF-8") from exc
        if b"\x00" in data:
            raise AttachmentValidationError("Text attachments cannot contain binary data")
    elif not valid_signature[normalized_type]:
        raise AttachmentValidationError("File content does not match its declared type")
    return clean_name


class LocalAttachmentStorage:
    """Private local storage; only authenticated API downloads expose file bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def new_key(self, extension: str) -> str:
        return f"{uuid4().hex[:2]}/{uuid4().hex}{extension.lower()}"

    def path_for(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise AttachmentValidationError("Stored attachment path is invalid")
        return target

    async def put(self, key: str, data: bytes) -> Path:
        target = self.path_for(key)

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await anyio.to_thread.run_sync(write)
        return target

    async def delete(self, key: str) -> None:
        target = self.path_for(key)

        def remove() -> None:
            target.unlink(missing_ok=True)

        await anyio.to_thread.run_sync(remove)
