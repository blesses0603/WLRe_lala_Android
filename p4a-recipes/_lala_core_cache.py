"""Build-only, SHA-256-gated reuse for eight isolated p4a Cython recipes.

This helper is copied only into disposable p4a recipe staging; it does not
ship as an application module or relax the signed APK audit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct

from pythonforandroid.recipe import CythonRecipe


# Pinned p4a builds target Python 3.14 through a Linux x86_64 host. Although
# the extension suffix says x86_64, the actual ELF must be Android ARM64.
ABI_SUFFIX = ".cpython-314-x86_64-linux-gnu.so"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arm64_shared_object(path: Path) -> bool:
    if not path.is_file() or path.is_symlink() or not 128 <= path.stat().st_size <= 32 * 1024 * 1024:
        return False
    with path.open("rb") as handle:
        header = handle.read(64)
    return (len(header) == 64 and header[:6] == b"\x7fELF\x02\x01"
            and struct.unpack_from("<H", header, 16)[0] == 3
            and struct.unpack_from("<H", header, 18)[0] == 183)


class SHA256CoreRecipe(CythonRecipe):
    """Use a locally verified ARM64 binary or perform the original build."""

    def build_arch(self, arch):
        recipe_root = Path(self.get_recipe_dir())
        base = recipe_root / "prebuilt"
        expected = recipe_root / ".p3expected"
        accepted = recipe_root / ".p3verified"
        extension = self.site_packages_name
        filename = extension + ABI_SUFFIX if isinstance(extension, str) else ""
        native = base / filename
        manifest = base / "manifest.json"
        pyx = recipe_root / "src" / (extension + ".pyx") if extension else None
        try:
            if (arch.arch == "arm64-v8a" and filename and
                    expected.is_file() and not expected.is_symlink() and
                    accepted.is_file() and not accepted.is_symlink() and
                    manifest.is_file() and not manifest.is_symlink() and
                    pyx is not None and pyx.is_file() and not pyx.is_symlink() and
                    arm64_shared_object(native)):
                key = expected.read_text(encoding="ascii").strip()
                approved = accepted.read_text(encoding="ascii").strip()
                record = json.loads(manifest.read_text(encoding="utf-8"))
                if (len(key) == 64 and key == approved and record == {
                        "schema": 1, "key": key, "module": extension,
                        "filename": filename, "source_sha256": sha256(pyx),
                        "binary_sha256": sha256(native),
                    }):
                    destination = Path(self.ctx.get_python_install_dir(arch.arch))
                    destination.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(native, destination / filename)
                    print("LALA_P3_VERIFIED_HIT " + self.name, flush=True)
                    return
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            pass
        print("LALA_P3_COMPILE " + self.name, flush=True)
        return super().build_arch(arch)
