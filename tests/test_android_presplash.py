"""Native Android splash regressions, independent of the Kivy widget tree."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image

from tools.android_presplash import validate_spec, verify_apk, report, SPEC


class AndroidPresplashTests(unittest.TestCase):
    def test_project_uses_compact_centered_native_splash(self):
        splash, color = validate_spec(SPEC)
        self.assertEqual(splash.as_posix().split("/")[-2:], ["assets", "presplash.png"])
        self.assertEqual(color.lower(), "#081626")
        with Image.open(splash) as image:
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(image.convert("RGB").getpixel((0, 0)), (8, 22, 38))
            # Upper third and outer border must be dark, not a full-bleed portrait.
            self.assertEqual(image.convert("RGB").getpixel((256, 100)), (8, 22, 38))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        asset = self.root / "assets" / "app.png"
        asset.parent.mkdir()
        Image.new("RGBA", (256, 256), (12, 125, 200, 255)).save(asset)
        self.asset = asset
        self.spec = self.root / "buildozer.spec"
        self.spec.write_text(
            "[app]\nicon.filename = assets/app.png\n"
            "presplash.filename = assets/presplash.png\n"
            "android.presplash_color = #081626\n", encoding="utf-8")
        self.splash, _ = validate_spec(self.spec)

    def apk_with_image(self, picture=None, resource="res/drawable/presplash.png"):
        apk = self.root / "test.apk"
        with zipfile.ZipFile(apk, "w") as out:
            if picture:
                out.write(picture, resource)
        return apk

    def test_matching_bundled_icon_and_report(self):
        apk = self.apk_with_image(self.splash)
        result = verify_apk(apk, self.spec)
        self.assertEqual(result["background"], "#081626")
        self.assertEqual(result["resolution"], "512x512")
        path = report(apk, self.spec)
        self.assertIn("Bundled icon comparison: PASSED", path.read_text())
        self.assertEqual(path.name, "PRESPLASH_INFO.txt")

    def test_kivy_stock_or_other_logo_is_rejected(self):
        wrong = self.root / "default_kivy.png"
        Image.new("RGBA", (512, 512), (0, 0, 0, 255)).save(wrong)
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_apk(self.apk_with_image(wrong), self.spec)

    def test_missing_native_resource_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected one native presplash"):
            verify_apk(self.apk_with_image(), self.spec)

    def test_missing_setting_or_black_background_is_rejected(self):
        self.spec.write_text(
            "[app]\nicon.filename = assets/app.png\n"
            "android.presplash_color = #081626\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "explicitly"):
            validate_spec(self.spec)
        self.spec.write_text(
            "[app]\nicon.filename = assets/app.png\n"
            "presplash.filename = assets/presplash.png\n"
            "android.presplash_color = #000000\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nonblack"):
            validate_spec(self.spec)


if __name__ == "__main__":
    unittest.main()
