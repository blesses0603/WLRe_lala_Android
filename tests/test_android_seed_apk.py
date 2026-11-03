"""SQLite must be byte-identical to the reviewed seed inside the actual APK payload."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile
from tools.android_seed_apk_audit import verify


class SeedAPKTests(unittest.TestCase):
    def fixture(self, rows):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        (root/'ANDROID').mkdir();raw=b'reviewed-resource-fixture'
        (root/'ANDROID/DESKTOP_SOURCE_LOCK.json').write_text(json.dumps(dict(seed=dict(path='wlre/resources/resource_catalog_seed.sqlite3',size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))))
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
            for name,data in rows:
                entry=tarfile.TarInfo(name);entry.size=len(data);tar.addfile(entry,io.BytesIO(data))
        apk=root/'fixture.apk'
        with zipfile.ZipFile(apk,'w') as archive:archive.writestr('assets/private.tar',buffer.getvalue())
        return root,apk

    def test_exact_seed_passes_and_duplicate_missing_or_modified_seed_fail(self):
        name='wlre/resources/resource_catalog_seed.sqlite3';raw=b'reviewed-resource-fixture'
        root,apk=self.fixture([(name,raw)])
        self.assertEqual(verify(apk,root=root),hashlib.sha256(raw).hexdigest())
        for rows in ([],[(name,raw),(name,raw)],[(name,raw[:-1]+b'x')],[(name,b'wrong-size')]):
            with self.subTest(rows=len(rows)):
                root,apk=self.fixture(rows)
                with self.assertRaises(ValueError):verify(apk,root=root)
