"""Android-private ciphertext store; AES key never leaves Android Keystore."""
import base64
import json
import os
import stat
from pathlib import Path


class AndroidCipher:
    alias = 'WLRe_LaLa.accounts.v1'

    def __init__(self):
        from jnius import autoclass, cast
        self.cls = autoclass
        self.store = autoclass('java.security.KeyStore').getInstance('AndroidKeyStore')
        self.store.load(None)
        if not self.store.containsAlias(self.alias):
            props = autoclass('android.security.keystore.KeyProperties')
            builder = autoclass('android.security.keystore.KeyGenParameterSpec$Builder')(
                self.alias, props.PURPOSE_ENCRYPT | props.PURPOSE_DECRYPT)
            builder.setKeySize(256)
            builder.setBlockModes(props.BLOCK_MODE_GCM)
            builder.setEncryptionPaddings(props.ENCRYPTION_PADDING_NONE)
            gen = autoclass('javax.crypto.KeyGenerator').getInstance('AES', 'AndroidKeyStore')
            gen.init(cast('java.security.spec.AlgorithmParameterSpec', builder.build()))
            gen.generateKey()
        self.key = cast('java.security.Key', self.store.getKey(self.alias, None))

    def encrypt(self, data):
        cipher = self.cls('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        cipher.init(1, self.key)
        encrypted = cipher.doFinal(data)
        return {'iv': base64.b64encode(bytes(int(b) & 255 for b in cipher.getIV())).decode(),
                'data': base64.b64encode(bytes(int(b) & 255 for b in encrypted)).decode()}

    def decrypt(self, record):
        cipher = self.cls('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        from jnius import cast
        spec = self.cls('javax.crypto.spec.GCMParameterSpec')(128, base64.b64decode(record['iv']))
        cipher.init(2, self.key, cast('java.security.spec.AlgorithmParameterSpec', spec))
        return bytes(int(b) & 255 for b in cipher.doFinal(base64.b64decode(record['data'])))


class AccountVault:
    def __init__(self, path, cipher):
        self.path, self.cipher = Path(path), cipher

    def load(self):
        # Never resolve a symlink into an external cleartext/attacker file.
        if not self.path.exists() and not self.path.is_symlink():
            return []
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Unsafe account vault file type")
            record = json.load(stream)
        return json.loads(self.cipher.decrypt(record).decode("utf-8"))

    def save(self, records):
        encrypted = self.cipher.encrypt(json.dumps(records, ensure_ascii=False).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise ValueError("Unsafe account vault directory")
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        # Exclusive temporary file creation rejects pre-planted links and
        # stale incomplete transactions rather than truncating them.
        fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(encrypted, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
