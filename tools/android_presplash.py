"""Validate the native Android presplash, not the later Kivy widget tree.

The SDL2 bootstrap renders res/drawable*/presplash before main.py runs.
Using icon.filename alone changes the launcher icon but leaves the generic
Kivy "Loading..." presplash in place.
"""
import configparser
import io
from pathlib import Path
import re
import sys
import zipfile

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "buildozer.spec"
PRESPLASH_ENTRY = re.compile(
    r"^res/drawable(?:-[A-Za-z0-9_-]+)?/presplash\.(?:png|jpe?g|webp)$",
    re.IGNORECASE,
)


def _draw_compact_splash(icon_path, destination, color):
    """Keep the icon itself unchanged, but show it smaller at app bootstrap."""
    with Image.open(icon_path) as original:
        mark = original.convert("RGBA")
    mark.thumbnail((196, 196), Image.Resampling.LANCZOS)
    background = Image.new("RGBA", (512, 512), tuple(
        int(color[i:i+2], 16) for i in (1, 3, 5)) + (255,))
    background.alpha_composite(mark, ((512-mark.width)//2, (512-mark.height)//2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    background.save(destination, format="PNG")


def validate_spec(spec=SPEC):
    spec = Path(spec)
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(spec, encoding="utf-8"):
        raise ValueError("Android buildozer.spec is missing")
    app = config["app"]
    source = app.get("presplash.filename", "").strip()
    icon = app.get("icon.filename", "").strip()
    color = app.get("android.presplash_color", "").strip()
    if not source or source == icon or Path(source).name != "presplash.png":
        raise ValueError("Native presplash must explicitly use a separate compact presplash.png")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) or color.lower() == "#000000":
        raise ValueError("Native presplash must use a nonblack six-digit background color")
    source_icon = spec.parent / icon
    if not source_icon.is_file():
        raise ValueError("Configured launcher icon PNG is missing")
    asset = spec.parent / source
    _draw_compact_splash(source_icon, asset, color)
    with Image.open(asset) as picture:
        if picture.format != "PNG":
            raise ValueError("Native presplash must be a PNG image")
        if min(picture.size) < 192:
            raise ValueError("Native presplash is too small")
    return asset, color


def verify_apk(apk, spec=SPEC):
    """Verify the bundled drawable matches our LaLa icon, not stock Kivy art."""
    asset, color = validate_spec(spec)
    apk = Path(apk)
    if not apk.is_file():
        raise ValueError("Built Android APK not found")
    with zipfile.ZipFile(apk) as archive:
        matches = [name for name in archive.namelist()
                   if PRESPLASH_ENTRY.fullmatch(name)]
        if len(matches) != 1:
            raise ValueError("Expected one native presplash resource in APK; found "
                             + str(len(matches)))
        resource = matches[0]
        with Image.open(io.BytesIO(archive.read(resource))) as packed:
            native = packed.convert("RGBA")
            native.load()
    with Image.open(asset) as original:
        logo = original.convert("RGBA")
        logo.load()
    if native.size != logo.size:
        raise ValueError("Bundled native presplash dimensions do not match generated splash")
    # Some Android resource compilers recompress PNGs. Compare decoded pixel
    # colors rather than file hashes, allowing tiny re-encoding differences.
    difference = ImageChops.difference(logo, native)
    mean_difference = sum(ImageStat.Stat(difference).mean) / 4
    if mean_difference > 3:
        raise ValueError("Bundled native presplash differs from the compact LaLa splash")
    return {
        "resource": resource,
        "image": asset.name,
        "background": color,
        "resolution": "{}x{}".format(*native.size),
        "mean_pixel_difference": round(mean_difference, 4),
    }


def report(apk, spec=SPEC):
    result = verify_apk(apk, spec)
    output = Path(apk).parent / "PRESPLASH_INFO.txt"
    lines = [
        "WLRe_LaLa native Android startup screen verification",
        "LaLa compact native splash: " + result["image"],
        "Launcher icon is unchanged; logo occupies no more than 196/512 of splash width.",
        "Bundled resource: " + result["resource"],
        "Background: " + result["background"],
        "Image dimensions: " + result["resolution"],
        "Bundled icon comparison: PASSED",
        "This replaces the stock Kivy Loading presplash before main.py runs.",
        "This does not prove the application will initialize on a physical phone.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Custom LaLa native presplash verified: {} on {}".format(
        result["resource"], result["background"]), flush=True)
    return output


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "check-spec":
        asset, color = validate_spec()
        print("LaLa native presplash configured: {} on {}".format(asset.name, color))
    elif len(sys.argv) == 3 and sys.argv[1] == "check-apk":
        report(sys.argv[2])
    else:
        raise SystemExit(
            "Usage: python tools/android_presplash.py check-spec | check-apk APK_PATH")
