"""Restore the pinned desktop SQLite seed before tests or APK staging.

The source commit and digest are reviewed in ANDROID/DESKTOP_SOURCE_LOCK.json.
No latest URL, credentials, gameplay state or signing material are used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def restore(root=ROOT, *, source_root=None, opener=urllib.request.urlopen):
    root = Path(root)
    lock = json.loads((root/'ANDROID/DESKTOP_SOURCE_LOCK.json').read_text(encoding='utf-8'))
    info = lock['seed']
    target = root/info['path']
    def valid(path):
        if not path.is_file() or path.stat().st_size != info['size']:
            return False
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024), b''):
                digest.update(chunk)
        return digest.hexdigest() == info['sha256']
    if valid(target): return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.seed-') as work:
        staged = Path(work)/'seed.sqlite3'
        if source_root is not None:
            shutil.copyfile(Path(source_root)/info['path'], staged)
        else:
            url = 'https://raw.githubusercontent.com/blesses0603/WLRe_lala/'+lock['desktop_source']+'/'+info['path']
            with opener(url, timeout=120) as response, staged.open('wb') as out:
                total = 0
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    if total > info['size']: raise ValueError('資料庫下載超過鎖定大小')
                    out.write(chunk)
        if not valid(staged): raise ValueError('桌面資源資料庫大小或 SHA-256 不符')
        if str(root) not in sys.path: sys.path.insert(0, str(root))
        from wlre.storage.full_resource_seed import verify_seed
        verify_seed(staged)
        staged.replace(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    print('初始資源資料庫已通過固定來源及內容校驗：', restore(source_root=args.source_root).name)
