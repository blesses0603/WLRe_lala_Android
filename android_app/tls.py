"""Verified CA setup shared by Android Activity and foreground service."""
import os
from pathlib import Path
import re
import ssl
import tempfile
from urllib.request import HTTPSHandler, build_opener

# Android 14+ stores system roots in the Conscrypt APEX; earlier versions
# expose the read-only system directory. Never read user-installed CA stores.
SYSTEM_CA_DIRS = (
    Path('/apex/com.android.conscrypt/cacerts'),
    Path('/system/etc/security/cacerts'),
)
_CA_NAME = re.compile(r'[0-9a-f]{8}\.[0-9]+\Z')



def verified_https_opener(redirect_handler):
    """Bind urllib to the Android-selected verified CA file explicitly.

    OpenSSL on some embedded builds does not apply SSL_CERT_FILE to its
    implicit default certificate lookup. Version checks already pass cafile
    explicitly; Manifests and Bundles must use the same verified trust roots.
    The caller supplies its existing strict no-redirect handler.
    """
    cafile = os.environ.get('SSL_CERT_FILE')
    context = (ssl.create_default_context(cafile=cafile) if cafile
               else ssl.create_default_context())
    return build_opener(redirect_handler, HTTPSHandler(context=context)).open


def configure_tls(root, *, system_dirs=None, cafile=None):
    """Select explicit, parsed roots while keeping normal TLS verification.

    No server certificate is downloaded or trusted here. Only the bundled
    Mozilla roots and Android's read-only system CA certificates are used.
    Each process calls this before starting resource/network workers.
    """
    if cafile is None:
        import certifi
        cafile = certifi.where()
    source = Path(cafile)
    base = source.read_bytes()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=base.decode('ascii'))
    if not context.cert_store_stats()['x509_ca']:
        raise ValueError('TLS CA bundle has no trusted certificate authorities')
    payloads = [base]
    seen = set()
    directories = SYSTEM_CA_DIRS if system_dirs is None else system_dirs
    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not _CA_NAME.fullmatch(path.name) or not path.is_file():
                continue
            data = path.read_bytes()
            if len(data) > 128 * 1024:
                raise ValueError('Android system CA certificate exceeds size limit')
            # Android's read-only system CA entries may be PEM or DER X.509.
            # OpenSSL validates every candidate before trusting it.
            pem = (data.decode('ascii') if data.startswith(b'-----BEGIN CERTIFICATE-----')
                   else ssl.DER_cert_to_PEM_cert(data))
            normalized = pem.encode('ascii')
            if normalized in seen:
                continue
            context.load_verify_locations(cadata=pem)
            seen.add(normalized)
            payloads.append(normalized)
    selected = source
    if seen:
        directory = Path(root) / 'tls'
        directory.mkdir(parents=True, exist_ok=True)
        selected = directory / 'cacert.pem'
        pending = None
        try:
            with tempfile.NamedTemporaryFile(
                    dir=directory, prefix='.ca-', delete=False) as stream:
                pending = Path(stream.name)
                stream.write(b'\n'.join(payloads) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, selected)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
    # setdefault could retain a missing host/build-machine CA path inherited
    # by the Android process. Requests and urllib must use the same bundle.
    os.environ['SSL_CERT_FILE'] = str(selected)
    os.environ['REQUESTS_CA_BUNDLE'] = str(selected)
    return selected
