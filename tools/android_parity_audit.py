"""Reject unnoticed drift from the reviewed desktop gameplay core."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    root=Path(root)
    lock=json.loads((root/'ANDROID/DESKTOP_SOURCE_LOCK.json').read_text(encoding='utf-8'))
    adaptations=lock.get('android_adaptations',{})
    for name,digest in lock['source_files'].items():
        expected=adaptations.get(name,{}).get('sha256',digest)
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('共用核心與已審查來源不一致：'+name)
    return len(lock['source_files'])


if __name__=='__main__':
    print('共用核心來源核對通過：',audit())
