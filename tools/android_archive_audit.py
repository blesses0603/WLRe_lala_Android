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

from cryptography import x509

KEY_HEADERS = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    rb"|-----BEGIN ENCRYPTED" + rb" PRIVATE KEY-----"
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
MAX_CA_BUNDLE_BYTES = 512 * 1024
CERT_BLOCK = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s*[A-Za-z0-9+/=\r\n]+"
    rb"-----END CERTIFICATE-----", re.ASCII,
)


def _public_ca_bundle_path(path: str) -> bool:
    """Only certifi's public CA bundle may have a PEM extension."""
    # python-for-android stores its installed packages below _python_bundle/
    # inside lib/arm64-v8a/libpybundle.so. Match only these complete paths:
    # never permit arbitrary prefix/suffix matches for *.pem files.
    return path.casefold() in (
        "certifi/cacert.pem",
        "site-packages/certifi/cacert.pem",
        "_python_bundle/site-packages/certifi/cacert.pem",
    )


def _validate_public_ca_bundle(data: bytes) -> None:
    """Require valid public X.509 PEM blocks and no extra credential material."""
    if not data or len(data) > MAX_CA_BUNDLE_BYTES or KEY_HEADERS.search(data):
        raise ValueError("Unsafe certifi CA bundle content")
    blocks = CERT_BLOCK.findall(data)
    if not blocks:
        raise ValueError("Unsafe certifi CA bundle content")
    try:
        for block in blocks:
            x509.load_pem_x509_certificate(block)
    except ValueError as exc:
        raise ValueError("Unsafe certifi CA bundle content") from exc
    remaining = CERT_BLOCK.sub(b"", data)
    # certifi prepends informational '# Issuer' comments to CA certificates.
    if any(line.strip() and not line.lstrip().startswith(b"#")
           for line in remaining.splitlines()):
        raise ValueError("Unsafe certifi CA bundle content")
    if b"-----BEGIN" in remaining or b"-----END" in remaining:
        raise ValueError("Unsafe certifi CA bundle content")


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
    normalized = "/".join(parts)
    public_ca = _public_ca_bundle_path(normalized)
    if any(part in BAD_NAMES or
           (PurePosixPath(part).suffix in BAD_EXTS and not (
               public_ca and part == "cacert.pem"))
           for part in lower):
        # Never include suspicious filenames or raw contents in CI messages.
        raise ValueError("Potential credential file in nested archive")
    return normalized


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
    if _public_ca_bundle_path(name):
        if size <= 0 or size > MAX_CA_BUNDLE_BYTES:
            raise ValueError("Unsafe certifi CA bundle size")
        data = stream.read(MAX_CA_BUNDLE_BYTES + 1)
        if len(data) != size:
            raise ValueError("Truncated certifi CA bundle")
        _peek_scan(data, limit)
        _validate_public_ca_bundle(data)
        return
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
