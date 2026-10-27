# Phase 0：Android 現況盤點與重製輸入

> 盤點基準：`main`，Android 版本 `v0.0.8`；參照提交 `e1767b33ac4e83dc60bd34539c3d2889380b861d`。
> 本文件是 GitHub 原始碼靜態盤點，不代表本回合已執行 Python 測試、APK 建置或實體手機驗收。
> 舊版只作為行為、協定及資料來源的證據，不直接沿用舊 UI／架構作為新產品骨架。

## 1. 盤點摘要

| 項目 | main 現況 | 對全新 LaLa 的決策 |
|---|---|---|
| 專案入口 | `main.py` 建立並執行 `android_app.app.LaLaApp` | 新版入口及 application identity 獨立決策，不覆寫既有 APK |
| UI／打包 | Kivy 2.3.1、Python、Pyjnius、Buildozer；`buildozer.spec` 與 `android_app/version.py` 均為 `0.0.8` | P0 先比較維護成本、生命週期及測試能力，不先決定沿用 Kivy 或改用其他 toolkit |
| Android 原生橋接 | `android_app/java/org/lala/client/` 含 `ConnectionService.java`、`FloatingOverlay.java`、`RuntimeIntegrity.java`；另有多個 python-for-android recipe | 前景服務、通知、Overlay、IPC、Keystore／簽章驗證須保留為明確平台層 |
| 專案規模 | 305 個 tree entries、191 個 Python 檔案、39 個測試 Python 檔、22 個 Markdown 檔、5 個 Actions workflow | P0 建立功能／測試矩陣，不把現存測試檔數當成所有功能已驗證 |
| 平台與版本 | README 標示 Android 12 以上、ARM64 手機測試版；固定簽章／SHA256 與 APK 驗收流程已有專門文件 | application ID、簽章及發佈相容性未決之前，不變更套件識別或正式建置秘密 |

## 2. 目前程式分層與入口

### UI／應用程式層

- `android_app/app.py`：Kivy App、啟動與恢復、權限及 UI 狀態；應避免在 UI callback 中累積網路／領域規則。
- `android_app/dashboard.py`、`automation_ui.py`、`overview_model.py`、`widgets.py`、`theme.py`：主畫面、帳號卡片、自動化入口、UI 元件及視覺樣式。
- `android_app/pages/`：現有頁面含地圖、屬性、夥伴、遠征、一般、實例、副產／製作、資源、設定及社交；main 目前沒有獨立的 `pages/battle.py`，戰鬥／自動化 UI 位於帳號卡片控制與相關模組。
- `android_app/features.py`：定義 IPC 可接受的操作種類及允許投影的狀態欄位，是重要邊界，重製時不應由 UI 任意略過。

### 服務、狀態與平台整合

- 共用候選核心副本：`wlre/core/`、`wlre/network/`、`wlre/services/`、`wlre/storage/`。
- Android 服務與會話：`android_app/service.py`、`runtime.py`、`sessions.py`、`vault.py`、`credentials.py`、`preferences.py`。
- 原生橋接與封裝：`android_app/java/`、`p4a-recipes/lalaclient`、`lalaprotocol`、`lalavault`、`lalawire` 等。
- 建置與安全檢查：`buildozer.spec`、`tools/android_signing.py`、`android_release_gate.py`、`android_phase10_acceptance.py`，以及 `ANDROID/SECURITY.md`、`SIGNING.md`、`PHASE09_RELEASE_GATE.md`、`PHASE10_FINAL_ACCEPTANCE.md`。

## 3. Battle（戰鬥）盤點

### 現有入口／核心

- UI 自動化入口：`android_app/automation_ui.py`；能力／狀態投影：`android_app/features.py`、`dashboard.py`。
- 共用候選服務：`wlre/services/battle/auto_battle.py`、`battle_commands.py`、`party.py`、`combat.py`、`companions.py`、`party_guard.py`。
- 共享事件與耗材協調：`wlre/core/state_battle_events.py`、`wlre/services/items/combat_resources.py`（若在目標版本存在）、`reservations.py`、`services/coordination.py` 及戰後維護。
- Battle 不是單純的自動戰鬥開關。新 UI 必須區分手動指令、自動規則、戰鬥狀態、耗材預留、伺服器回覆與不確定結果。

### Android 特有驗收案例

1. 切到背景、鎖屏、系統回收程序、回到前景時，戰鬥狀態及操作等待狀態一致；不得因畫面重建重送命令。
2. 連線中斷／恢復、服務啟停、通知權限變動、帳號登出或切換角色時，取消與重置規則明確。
3. 手動操作與自動戰鬥同時觸發時有單一仲裁者；未知結果不允許自動重試。
4. 角色／夥伴／目標資料不完整或過期時，禁用不安全指令並呈現可理解原因。
5. UI 回報成功必須來自已定義的伺服器／狀態事件，不因 callback 執行成功而宣稱操作成功。

## 4. Map（地圖）盤點

- 主頁：`android_app/pages/map.py`；畫布 `MapCanvas` 同時負責地圖繪製、投影、點選座標及角色／標記顯示。
- 地圖／傳點服務：`wlre/services/world/minimap.py`、`map_names.py`、`display_position.py`、`navigation.py`、`portals.py`、`portal_policy.py`、`portal_travel.py`。
- 地圖頁包含座標選取、移動／停止移動與傳點相關 UI 操作。新產品需要將畫布、座標轉換、場景狀態、導航規劃與執行命令分離，不能直接把目前 callback 當成已驗證的領域流程。
- `wlre/resources/` 內的 `smallmaps.zip`、`navigation_data.zip`、`map_names.json`、`portals.json` 等資料應各自記錄版本、來源、schema 和驗證狀態。地圖能畫出來不代表座標、路徑或傳點已能在正式伺服器正確執行。

## 5. 桌面／Android 核心差異與風險

在兩個 repository 的 main tree 靜態比較中，存在 136 個相同相對路徑；這只能表示檔案路徑重疊，不能表示檔案內容一致或已有正式共用套件。實際核對到：

- 桌面 `wlre/__init__.py` 的內部版本為 `0.6.1`；Android 副本為 `0.0.6`，而 Android 發行版本另由 `android_app/version.py` 與 `buildozer.spec` 維護為 `0.0.8`。這是需明確定義的版本責任，不可把三者混為一個版本。
- 桌面與 Android 的 `wlre/network/protocol.py` 不完全相同；桌面已匯入若干 Android 副本沒有的解碼器／服務（例如帳篷與 NPC effect 相關依賴），顯示兩邊核心可能隨功能移植而分歧。
- Android 已有 `tests/test_android_desktop_parity.py`，但目標重製仍需以明確的共用 contract、同一份 golden cases 及兩平台各自的 adapter 測試作為 parity 基礎，不能只靠檔案同步。
- 新版建議採「共用、平台無關的協定／領域契約」加「Desktop adapter／Android adapter」；不要把整個 `wlre` 複製成共享目標，也不要讓 Android UI 直接操作封包。

## 6. 生命週期、安全及發佈限制

| 項目 | 現況／風險 | 重製要求 |
|---|---|---|
| 背景連線 | 前景服務、通知與 UI lifecycle 相互影響 | 明確定義 service owner、啟停、重連、取消、前景恢復與程序死亡行為 |
| 懸浮視窗 | Overlay 需獨立權限與原生視窗生命週期 | 獨立平台 adapter；拒絕權限後仍可使用主 App，狀態需可恢復 |
| 帳密 | 有 `credentials.py`、`vault.py` 與原生 Vault recipe | 以 Keystore 保護、限制備份與日誌，並覆蓋鑰匙失效／恢復錯誤 |
| 簽章／套件識別 | README／`ANDROID/SIGNING.md` 已描述固定簽章、SHA256 pin 和版本升級要求；`buildozer.spec` 的 package domain 為 `org.lala.client` | 未經明確決策不可改 application ID、簽章憑證、密鑰或 Release 流程 |
| 測試與 APK | 5 個 workflow；`android-smoke.yml` 為快速 Python／安全 preflight，不會因此產生 APK；完整 ARM64 APK workflow 為手動／符合版本 Tag 的流程 | 分開記錄 Python CI、APK build、APK 簽章驗證、安裝啟動、實機功能與正式服 E2E |
| 目標裝置 | README 標示 Android 12+、ARM64 測試版 | P0 定義最低／目標 Android API、ABI、裝置及權限矩陣；目前資訊以 README 為現況，不等於完整支援保證 |

## 7. Phase 0 交付狀態

| 工作項目 | 狀態 | 證據／下一步 |
|---|---|---|
| Android 原始碼／建置／測試清單 | 已完成靜態盤點 | main tree 與本文件；未執行本機測試 |
| Battle UI／核心責任切分 | 部分完成 | 目前 UI 與服務已有位置，但需補狀態圖、請求／回覆矩陣及 lifecycle 案例 |
| Map UI／移動／傳點切分 | 部分完成 | 目前畫布與操作入口存在；來源等級及正式服驗收狀態需逐項列明 |
| 共用核心範圍與版本政策 | 待 ADR | 對照桌面主線與 Android 副本；定義共用 contract，不把內部 package version 當發行版本 |
| Android 生命週期測試矩陣 | 待完成 | 背景／前景、鎖屏、程序回收、網路切換、權限撤銷、服務重啟 |
| 新版 UI toolkit／application ID／簽章決策 | 未決策（刻意保留） | P0 不變更現有 app ID、簽章、密鑰或 APK 發佈流程 |
| APK／真機／正式服驗收 | 未在本回合執行 | 後續分別留存建置證據、簽章／SHA256、裝置型號／Android 版本與結果 |

## 8. Phase 0 完成門檻

開始 Phase 1 新骨架前，至少要有：

- [ ] Battle 與 Map 狀態圖、命令／事件表、背景／前景與錯誤矩陣。
- [ ] 共用核心 contracts、Android 平台 adapter 邊界及版本責任 ADR。
- [ ] Android API／ABI／權限與生命週期測試矩陣。
- [ ] application ID、簽章／資料遷移策略的決策記錄；決策前不改既有發布身分。
- [ ] 一組可在無 Android 裝置情況下執行的共同 golden tests，以及 Android 專屬 adapter 測試。

## 9. 本次執行紀錄

- 讀取 main tree、README、入口、Buildozer 設定、Android UI／服務／版本檔、戰鬥／地圖代表模組、測試與 workflow 結構。
- 只記錄靜態盤點與風險，未修改既有功能程式碼、未調整版本號、未變更 app ID／簽章、未建立 Release／Tag。
- 本回合沒有執行本機 Python 測試、APK 打包、APK 安裝、實體手機測試或正式服 E2E。
