"""Phase07 installed-APK integrity gate for both Activity and service.

Do not print exception details: they can contain private paths/device details.
This is self-checking signer consistency, not root, hook, or server attestation.
"""
class IntegrityRejected(RuntimeError):
    """Sanitized signal that no session, vault or foreground IPC may start."""


def verify(context, *, loader=None):
    """Return one of a constrained set of codes, never a fingerprint or exception."""
    try:
        if loader is None:
            from jnius import autoclass
            loader = autoclass
        guard = loader("org.lala.client.RuntimeIntegrity")
        result = str(guard.status(context))
        if result == "OK":
            return "OK"
    except Exception:
        return "VERIFY_FAILED"
    return "REJECTED"


def require_integrity(context, *, loader=None):
    if verify(context, loader=loader) != "OK":
        raise IntegrityRejected("Android 安裝完整性驗證未通過（A07）")
    return True
