"""Stage-three Android-only real UI and safety regressions.

CI runs AST/source contract checks without an Android device, plus real Kivy
widget smoke tests where the Xvfb test runner provides a display.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("expedition", "instances", "production",
         "npc", "storage", "benefits", "settings")


def read(name):
    return (ROOT / "android_app" / "pages" / (name + ".py")).read_text("utf-8")


class StageThreeOfflineTests(unittest.TestCase):
    def test_all_changed_pages_and_editor_parse(self):
        for path in (
            *(f"android_app/pages/{name}.py" for name in PAGES),
            "android_app/settings_ui.py",
            "android_app/refresh_policy.py",
            "tests/test_android_refresh_policy.py",
        ):
            with self.subTest(path=path):
                ast.parse((ROOT / path).read_text("utf-8"), filename=path)

    def test_all_eight_feature_areas_use_actual_kivy_cards(self):
        for name in PAGES:
            with self.subTest(page=name):
                self.assertIn("feature_card(", read(name))
        for name, title in (
            ("expedition", "'自動派遣條件'"),
            ("instances", "'伺服器房間'"),
            ("production", "'材料槽位'"),
            ("npc", "'NPC 對話'"),
            ("storage", "'存取狀態'"),
            ("benefits", "'魔方自動開啟'"),
            ("settings", "'基本與戰鬥規則'"),
        ):
            with self.subTest(name=name):
                self.assertIn(title, read(name))
        self.assertIn("feature_card(", (ROOT / "android_app/settings_ui.py").read_text("utf-8"))

    def test_reuses_existing_commands_and_confirmations(self):
        checks = {
            "expedition": (
                "validate(value)", "self.d.preferences(preferences)",
                "start_expedition", "stop_expedition",
                "available_quests(self.state", "recovery_stock(",
            ),
            "instances": (
                "'instance_create'", "'instance_join'",
                "'instance_refresh'", "'instance_reward_claim'",
                "'instance_auto_reward'", "'instance_reward_cancel'",
                "self._send(", "not self.d.live",
            ),
            "production": (
                "'start_alchemy'", "'stop_alchemy'",
                "prepare(state, command)", "material_problem(",
                "recipe_plan(", "validate_rows(", "'plan_pause'",
            ),
            "npc": (
                "current_catalog_token()", "'npc_choose'",
                "'npc_close_shop'", "'npc_close_choice'",
                "'npc_approach'", "shop_catalog(",
            ),
            "storage": (
                "identity(item) != identity(expected)",
                "plan_transfer(", "transfer_command(",
                "bag_revision=bag_revision", "storage_revision=storage_revision",
                "self.d.send(command)",
            ),
            "benefits": (
                "'time_cube'", "self.rendering = True",
                "cube.get('ready')", "not cube.get('pending')",
                "not cube.get('uncertain')",
            ),
            "settings": (
                "'一般設定'", "'角色規則'", "'夥伴規則'",
                "'HP／SP補給'", "'必要成員'", "'修理／整理'",
                "'匯入／匯出'", "'ai_settings' not in self.d.data",
                "SettingsEditor(self.d.app,self.d.sid,tab)",
            ),
        }
        for name, tokens in checks.items():
            current = read(name)
            for token in tokens:
                with self.subTest(page=name, token=token):
                    self.assertIn(token, current)
        editor = (ROOT / "android_app/settings_ui.py").read_text("utf-8")
        for token in ("self.value = validate(draft)",
                      "self.app.manager.save_ai_settings(",
                      "self.popup.dismiss()", "self.collect()"):
            self.assertIn(token, editor)

    def test_no_fake_live_or_auto_paid_actions(self):
        for name in PAGES:
            text = read(name)
            with self.subTest(page=name):
                self.assertNotIn("verify=False", text)
                self.assertNotIn("lalaplayer01", text)
                self.assertNotIn("官方資源已驗證", text)
        instances = read("instances")
        self.assertIn("付費寶箱禁止自動購買", instances)
        self.assertIn("confirm_cost=True", instances)
        self.assertIn("instance_reward_cancel", instances)

    def test_time_cube_gets_1_hz_render_without_ipc_delay(self):
        from android_app.refresh_policy import RefreshPolicy, PERIODS
        self.assertEqual(PERIODS["福利"], 1.0)
        policy = RefreshPolicy()
        self.assertTrue(policy.should_refresh("福利", 1, True, 0))
        self.assertFalse(policy.should_refresh("福利", 1, True, .9))
        self.assertTrue(policy.should_refresh("福利", 1, True, 1.0))
        self.assertTrue(policy.should_refresh("福利", 2, False, 1.05))

    def test_alchemy_detail_is_not_overwritten_by_refresh(self):
        expeditions = read("expedition")
        self.assertIn("self.quest_detail.text =", expeditions)
        self.assertIn("self.status.text =", expeditions)
        self.assertNotIn("self.status.text = (\"{}｜所需", expeditions)


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and Xvfb/desktop display")
class StageThreeKivyTests(unittest.TestCase):
    def dashboard(self, page, *, state=None, live=False):
        sent = []
        d = SimpleNamespace(
            page_name=page, state=state if state is not None else {},
            data={}, live=live, closed=False,
            message=SimpleNamespace(text=""),
            send=lambda *args: sent.append(args) or True,
        )
        return d, sent

    def test_time_cube_never_dispatches_during_refresh(self):
        from android_app.pages.benefits import Benefits
        d, sent = self.dashboard("福利")
        view = Benefits(d)
        view.refresh()
        self.assertTrue(view.open_button.disabled)
        self.assertEqual(sent, [])
        d.state["time_cube"] = {
            "ready": True, "enabled": False, "count": 1,
            "pending": False, "uncertain": False, "status": "已同步",
        }
        d.live = True
        view.refresh()
        self.assertEqual(sent, [])
        self.assertFalse(view.open_button.disabled)
        view.auto.active = True
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], {
            "type": "time_cube", "action": "auto", "enabled": True,
        })

    def test_storage_switch_resets_stale_selection(self):
        from android_app.pages.storage import Storage
        d, sent = self.dashboard("儲藏存取")
        view = Storage(d)
        view.refresh()
        self.assertTrue(view.submit_button.disabled)
        view.selected = ("garage", "deposit", 1, {}, 1, 1)
        view.action.text = "取出"
        self.assertIsNone(view.selected)
        self.assertEqual(sent, [])

    def test_alchemy_five_slots_do_not_dispatch_on_open(self):
        from android_app.pages.production import Alchemy
        d, sent = self.dashboard("煉金")
        view = Alchemy(d)
        self.assertEqual(len(view.slots), 5)
        self.assertEqual(view.materials, [None]*5)
        self.assertEqual(sent, [])

    def test_settings_hub_provides_exact_seven_original_tabs(self):
        from android_app.pages.settings import SettingsPage
        from android_app.settings_ui import SettingsEditor
        d, sent = self.dashboard("AI與補給設定")
        view = SettingsPage(d)
        self.assertEqual(len(SettingsEditor.TABS), 7)
        self.assertGreaterEqual(len(view.children), 4)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
