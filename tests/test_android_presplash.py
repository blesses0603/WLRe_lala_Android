"""Native Android splash regressions, independent of the Kivy widget tree."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image

from tools.android_presplash import validate_spec, verify_apk, report, SPEC


class AndroidPresplashTests(unittest.TestCase):
    def test_project_uses_same_app_icon_for_native_splash(self):
        icon, color = validate_spec(SPEC)
        self.assertEqual(icon.as_posix().split("/")[-2:], ["assets", "app.png"])
        self.assertEqual(color.lower(), "#081626")
        self.assertTrue(icon.is_file())

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
            "presplash.filename = assets/app.png\n"
            "android.presplash_color = #081626\n", encoding="utf-8")

    def apk_with_image(self, picture=None, resource="res/drawable/presplash.png"):
        apk = self.root / "test.apk"
        with zipfile.ZipFile(apk, "w") as out:
            if picture:
                out.write(picture, resource)
        return apk

    def test_matching_bundled_icon_and_report(self):
        apk = self.apk_with_image(self.asset)
        result = verify_apk(apk, self.spec)
        self.assertEqual(result["background"], "#081626")
        self.assertEqual(result["resolution"], "256x256")
        path = report(apk, self.spec)
        self.assertIn("Bundled icon comparison: PASSED", path.read_text())
        self.assertEqual(path.name, "PRESPLASH_INFO.txt")

    def test_kivy_stock_or_other_logo_is_rejected(self):
        wrong = self.root / "default_kivy.png"
        Image.new("RGBA", (256, 256), (0, 0, 0, 255)).save(wrong)
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
            "presplash.filename = assets/app.png\n"
            "android.presplash_color = #000000\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nonblack"):
            validate_spec(self.spec)


if __name__ == "__main__":
    unittest.main()
