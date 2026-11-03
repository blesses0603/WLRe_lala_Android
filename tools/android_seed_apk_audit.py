"""Verify the exact reviewed initial database actually entered the APK."""
from pathlib import Path
import argparse
import hashlib
import json
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPORT='SHARED_RESOURCE_INFO.txt'


def verify(apk, *, root=ROOT):
    lock=json.loads((Path(root)/'ANDROID/DESKTOP_SOURCE_LOCK.json').read_text(encoding='utf-8'))
    expected=lock['seed'];count=0
    with zipfile.ZipFile(apk) as package:
        if 'assets/private.tar' not in package.namelist():raise ValueError('Missing APK application archive')
        with package.open('assets/private.tar') as compressed:
            with tarfile.open(fileobj=compressed,mode='r|*') as archive:
                for member in archive:
                    name=member.name.removeprefix('./')
                    if name!=expected['path']:continue
                    if not member.isfile() or member.size!=expected['size']:
                        raise ValueError('APK SQLite resource type or size mismatch')
                    stream=archive.extractfile(member);digest=hashlib.sha256();total=0
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        total+=len(chunk);digest.update(chunk)
                    if total!=expected['size'] or digest.hexdigest()!=expected['sha256']:
                        raise ValueError('APK SQLite resource digest mismatch')
                    count+=1
    if count!=1:raise ValueError('APK must contain exactly one reviewed SQLite seed')
    return expected['sha256']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('apk',type=Path)
    args=parser.parse_args();digest=verify(args.apk)
    (args.apk.parent/REPORT).write_text('Pinned shared SQLite seed in APK: VERIFIED\nSHA256: '+digest+'\nAndroid runtime and live server acceptance: NOT CLAIMED\n',encoding='utf-8')
