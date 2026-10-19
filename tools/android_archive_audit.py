"""Phase06 bounded, recursive package audit (no extraction and no secret logging).

Audits APK members plus p4a private.tar/libpybundle.so, nested ZIP/TAR payloads
and known credential signatures. This is a best-effort static check, not a
binary code analysis or a guarantee against runtime memory disclosure.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import zipfile

KEY_HEADERS = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    rb"|-----BEGIN ENCRYPTED PRIVATE KEY-----"
    rb"|AKIA[A-Z0-9]{16}"
    rb"|gh(?:p|o|u|s|r)_[A-Za-z0-9_]{30,}"
)
BAD_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "google-services.json", "service-account.json", "credentials.json",
}
BAD_EXTS = {".keystore", ".jks", ".p12", ".pfx", ".pem", ".p8", ".key", ".asc"}
TEXT_EXTS = {".txt", ".ini", ".xml", ".json", ".yaml", ".yml", ".properties",
             ".cfg", ".conf", ".csv", ".py", ".java", ".env", ".lua"}
ZIP_EXTS = (".zip", ".whl", ".jar", ".apk")
TAR_EXTS = (".tar", ".tar.gz", ".tgz")
MAX_DEPTH = 4
MAX_ITEMS = 20000
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_NESTED_BYTES = 24 * 1024 * 1024
MAX_SCAN_TOTAL = 64 * 1024 * 1024


@dataclass
class Limits:
    items: int = 0
    bytes_seen: int = 0
    archives: int = 0
    text_files: int = 0

    def item(self):
        self.items += 1
        if self.items > MAX_ITEMS:
            raise ValueError("Phase06 archive member count limit exceeded")

    def budget(self, count):
        self.bytes_seen += count
        if self.bytes_seen > MAX_SCAN_TOTAL:
            raise ValueError("Phase06 nested audit byte limit exceeded")


def _safe(name: str, *, directory: bool = False) -> str:
    if not isinstance(name, str) or "\x00" in name:
        raise ValueError("Unsafe nested archive member name")
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    parts = name.rstrip("/").split("/")
    if (not name or name.startswith("/") or
            any(part in ("", ".", "..") for part in parts) or
            re.match(r"^[a-zA-Z]:", name)):
        raise ValueError("Unsafe nested archive member path")
    lower = [p.casefold() for p in parts]
    if (any(p in BAD_NAMES or PurePosixPath(p).suffix in BAD_EXTS for p in lower)):
        raise ValueError("Potential credential file in nested archive")
    return "/".join(parts)


def _nested_type(name: str) -> str | None:
    lower = name.lower()
    if lower.endswith(ZIP_EXTS):
        return "zip"
    if lower.endswith(TAR_EXTS):
        return "tar"
    return None


def _is_text(name: str) -> bool:
    name = name.lower()
    return PurePosixPath(name).suffix in TEXT_EXTS


def _peek_scan(data: bytes, limit: Limits):
    limit.budget(len(data))
    if KEY_HEADERS.search(data):
        # Never echo matching content or full file paths in CI logs.
        raise ValueError("Private credential material detected in APK payload")
    limit.text_files += 1


def _tar(fileobj, label: str, limit: Limits, depth: int, inspect_name):
    if depth > MAX_DEPTH:
        raise ValueError("Phase06 nested archive depth exceeded")
    limit.archives += 1
    seen = set()
    try:
        with tarfile.open(fileobj=fileobj, mode="r|*") as archive:
            for member in archive:
                limit.item()
                name = _safe(member.name, directory=member.isdir())
                canonical = name.casefold()
                if canonical in seen:
                    raise ValueError("Duplicate nested archive member")
                seen.add(canonical)
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    raise ValueError("Unsafe nested TAR member type")
                inspect_name(name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("Unsupported nested TAR entry type")
                f = archive.extractfile(member)
                if f is None:
                    raise ValueError("Unreadable nested TAR entry")
                _payload(f, member.size, name, limit, depth, inspect_name)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ValueError("Corrupt nested TAR archive") from exc


def _zip(fileobj, label: str, limit: Limits, depth: int, inspect_name):
    if depth > MAX_DEPTH:
        raise ValueError("Phase06 nested archive depth exceeded")
    limit.archives += 1
    seen = set()
    try:
        with zipfile.ZipFile(fileobj) as archive:
            for member in archive.infolist():
                limit.item()
                name = _safe(member.filename, directory=member.is_dir())
                canonical = name.casefold()
                if canonical in seen:
                    raise ValueError("Duplicate nested archive member")
                seen.add(canonical)
                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise ValueError("Nested ZIP symlink not allowed")
                inspect_name(name)
                if member.is_dir():
                    continue
                with archive.open(member) as f:
                    _payload(f, member.file_size, name, limit, depth, inspect_name)
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
        raise ValueError("Corrupt nested ZIP archive") from exc


def _payload(stream, size: int, name: str, limit: Limits, depth: int, inspect_name):
    kind = _nested_type(name)
    if kind is not None:
        if depth >= MAX_DEPTH or size > MAX_NESTED_BYTES:
            raise ValueError("Nested archive exceeds Phase06 safety limits")
        data = stream.read(MAX_NESTED_BYTES + 1)
        if len(data) != size or len(data) > MAX_NESTED_BYTES:
            raise ValueError("Incomplete or oversized nested archive")
        limit.budget(len(data))
        if kind == "zip":
            _zip(io.BytesIO(data), name, limit, depth + 1, inspect_name)
        else:
            _tar(io.BytesIO(data), name, limit, depth + 1, inspect_name)
    elif _is_text(name) and size <= MAX_TEXT_BYTES:
        chunk = stream.read(MAX_TEXT_BYTES + 1)
        if len(chunk) != size:
            raise ValueError("Truncated text member")
        _peek_scan(chunk, limit)


def audit_apk(apk, inspect_name=lambda name: None):
    """Recursively inspect archive members and bounded text payloads.

    libpybundle.so is a p4a TAR despite its .so suffix. Its content MUST be
    audited, without reading the entire payload into memory.
    """
    limit = Limits()
    with zipfile.ZipFile(apk) as outer:
        seen = set()
        for member in outer.infolist():
            limit.item()
            name = _safe(member.filename, directory=member.is_dir())
            canonical = name.casefold()
            if canonical in seen:
                raise ValueError("Duplicate APK archive member")
            seen.add(canonical)
            inspect_name(name)
            if member.is_dir():
                continue
            with outer.open(member) as stream:
                if name in ("assets/private.tar", "lib/arm64-v8a/libpybundle.so"):
                    _tar(stream, name, limit, 0, inspect_name)
                else:
                    _payload(stream, member.file_size, name, limit, 0, inspect_name)
    return {"nested_archives": max(0, limit.archives - 2),
            "audited_containers": limit.archives,
            "scanned_text_files": limit.text_files,
            "inspected_entries": limit.items}
