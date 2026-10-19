## 同步 2026-10-18 桌面 main 新功能

基準：`blesses0603/WLRe_lala` 的提交 `c6bee236f0074f1981f29e957785beffe21f0ed8`，只移植跨平台核心與 Android 專用觸控頁面。

- 「夥伴出戰」：檢視出戰條件、手動出戰／休息，收到 S19 伺服器回覆後才更新。
- 「遠征」：內建 1262 官方 260 任務與 10 級、駐紮所和任務資料、好友度補充、出發及結算；設定依帳號／伺服器保存，但不自動開始。正式服派遣與領獎尚待驗證。
- 「包包與特技」：手機 4×6 每頁 24 格、64dp 物品原圖、資訊卡；超空間袋只能讀取 S62 已同步的遠端儲藏資料，沒有經驗證的寄取操作一律不提供。
- 「AI與補給設定」：新增修理／整理頁，包含 2 種修理道具、15 種整理物品及耐久門檻。真正自動修理、賣出或丟棄仍由共用核心檢查伺服器確認，不會僅因 UI 切換就執行。
- 原版遊戲圖示：帳號角色功能頁提供可左右滑動的操作捷徑。
- 真機測試：請特別檢查新增的多帳號遠征隔離、文字輸入、鎖屏後自動化存續，及遠端儲藏資料是否已同步。模擬器不會登入真實遊戲帳號。

# 飄流 RE:LaLa｜Android 使用與技術指南

本文件集中說明 Android 客戶端的**操作流程、權限、背景機制、APK 建置及驗收限制**。首次安裝與下載入口請先閱讀 [專案首頁 README](../README.md)；功能逐項對照請參考 [FEATURE_PARITY.md](FEATURE_PARITY.md)。

**開發中版本：v0.0.8** ｜ **最低 Android 12（API 31）** ｜ **只建置 ARM64 手機 APK** ｜ **Debug 測試用途**

> 請勿安裝早期 v0.0.2／v0.0.3 的舊 APK：歷史紀錄曾確認 Keystore／PyJNIUS JNI 初始化崩潰。v0.0.7 新增的懸浮小球與遊戲自動化操作仍需真機驗收；「Actions 成功」不等於正式遊戲連線驗收。

## 操作流程

### Android 原生啟動畫面

手機開啟 APK 時，Kivy 主畫面還沒建立，會先顯示 python-for-android SDL2 的原生 `presplash`。原本 `buildozer.spec` 只有設定 App ICON，沒有設定 `presplash.filename`，因此手機仍顯示 Kivy 預設黑底 `Loading...`。目前已指定與 App 相同的 `android_app/assets/app.png`，並設定深藍背景 `#081626`。

完整 APK 建置流程會在編譯後檢查 APK 內的 `res/drawable*/presplash` 圖片是否與 LaLa ICON 相符，通過後才上傳；Artifact 中另附 `PRESPLASH_INFO.txt`。**此修改只改啟動圖案，並不能修復真正卡在 Loading 的崩潰或初始化失敗**。若新版本停留在啟動畫面超過一分鐘，請提供手機 Logcat 供進一步定位。

### 1. 安裝及開始登入

1. 從 [手動／Tag APK 建置流程](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) 的成功執行紀錄下載帶版本號的 ARM64 APK；舊版的 [ARM64 Artifact](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39141939393) 可在尚未過期時使用。日常 [快速測試流程](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) **不再上傳 APK**。
2. 解壓後確認 APK 與 `SHA256SUMS.txt`，在 ARM64 Android 12 以上手機安裝測試包。
3. 啟動程式、選擇地球／水星及分流，輸入帳號與密碼後登入。帳號驗證、角色清單與角色入場須等待伺服器實際回覆。
4. 可新增多個獨立連線；各帳號各自擁有停止旗標、指令佇列與狀態，不將一個帳號的操作轉送給另一個帳號。
5. 入場後在帳號卡片啟動／停止自動戰鬥或徘徊，也可開啟角色功能，操作戰場、地圖、補給、社交與製作等頁面。

停止某個帳號不等於停止其他帳號；「停止全部連線與服務」會關閉整個連線服務。若服務尚未就緒或已失去回應，UI 應顯示未知或失聯，不以先前快照冒充目前在線。

### 2. 前景通知及背景連線

App 回到前景時會重新建立 Kivy 畫面，恢復帳號／伺服器欄位與原角色功能頁，再從仍在執行的連線服務讀取帳號快照。此動作不重新登入、不重啟遊戲服務，亦不保存背景期間輸入的明文密碼。若手機仍出現全空白主畫面，請提供當次 Logcat 的 `WLRE_ANDROID_UI_RESTORE_` 診斷標記。

本專案不是單靠 Kivy 畫面維持連線。`android_app/service.py` 啟動獨立的 Python 前景服務程序，在服務端管理多帳號連線；`android_app/runtime.py` 使用 App 私有 Unix socket 將畫面操作交給服務處理。

- 畫面暫停、切換到其他 App 或 Activity 重建時，前景服務可繼續管理連線；使用者重新開啟畫面後可取回狀態。
- 系統前景通知提供返回 App 與停止全部連線的入口。通知的常駐標記不能保證 Android 不允許使用者移除。
- 活動連線時使用**有期限的 partial wake lock**，並透過 TCP keepalive 協助偵測網路中斷；兩者都不是永久在線的保證。
- Android 15 的 `dataSync` 類型前景服務在適用條件下有每 24 小時累計約 **6 小時** 的背景執行時限；系統停止服務後不會擅自用儲存帳密重新登入。
- 網路切換、省電模式、Doze、廠商背景限制及使用者在系統設定強制停止 App，都可能中斷服務。長時間行為須逐台手機驗證。
- 裝置電池、記憶體、喚醒鎖等監控讀取如果失敗，只會回報監控異常，不會因為監控本身的例外直接關閉 IPC 服務或所有角色連線。

### 3. 懸浮小球（v0.0.7）

**懸浮球是選用的狀態介面，不是另一條遊戲連線，也不能替代前景服務通知。**

1. 開啟 App → **服務與資源** → **開啟懸浮小球（需額外授權）**。
2. 系統開啟「顯示在其他應用程式上層」設定時，允許本 App 使用；返回程式，等待背景服務同步設定。
3. 小球可以拖曳至螢幕其他位置，點擊小球展開狀態面板。
4. 小球沿用 App 原本的 ICON 並顯示在線數徽記。展開的科技風格「角色概況」卡片顯示在線／活動／總帳號數，以及各帳號實際同步的角色、夥伴、Lv.、HP／SP 數值與進度條、自動戰鬥、自動徘徊與事件狀態；卡片可捲動，亦可返回 App 或收合面板。
5. 點「隱藏懸浮小球（不斷線）」或回到「服務與資源」關閉小球；**不會因單純關閉小球而停止遊戲連線**。

顯示在其他 App 上層時，帳號名稱會遮罩，不顯示密碼、聊天內文或憑證；狀態面板最多列出六筆帳號、每筆前五位角色／夥伴資料，其餘顯示數量；斷線後不顯示舊角色詳細資料。當權限被撤銷或前景服務結束，小球可能消失；普通 Android App 無法禁止使用者或系統關閉它。

主 App 介面統一採用深藍圓角科技主題：帳號卡片、操作按鈕、角色功能頁、文字輸入框、下拉選單及選項、核取圓鈕和設定視窗皆使用共用圓角樣式，且有按下與停用狀態。懸浮球只保留戰鬥、徘徊及事件；**煉金、製作、補給仍顯示在主 App 的角色概況**，但不傳入懸浮面板。

懸浮權限與 Android 13 以上的**通知權限**是不同設定。通知權限在系統要求時處理，懸浮權限只在使用者主動開啟小球時要求。**安裝 APK 並不會自動取得懸浮權限**。

### 4. 帳號與設定資料

- **帳號保存是自願選項**：勾選「加密保存帳密」時，使用 Android Keystore 的 AES-256-GCM 加密後，儲存在 App 私有、不備份的檔案位置；未勾選則不保存密碼。
- Keystore 金鑰不可匯出。解除安裝、清除 App 資料、換機或系統金鑰失效，都可能導致舊密文無法恢復。不要把此機制當作跨裝置備份。
- 自動戰鬥 AI 與偏好依帳號及伺服器保存，重新登入可載入，但**不會自動啟動戰鬥或徘徊**。
- 畫面與服務之間使用私有 Unix socket；沒有開放外部 TCP 控制埠。帳密不得寫入日誌、聊天事件或公開通知。
- 事件歷史與聊天紀錄在服務內做有限長度保存；若服務終止，不應假設未另存的記錄可永久保留。
- 聊天僅在收到伺服器發話結果為成功時才清除相同草稿；發話被拒絕、IPC 結果不明或伺服器長時間沒有回覆時，保留原文字並解除送出按鈕。因協定不支援端到端已讀確認，仍不保證對方已收到。
- IPC 失聯不會自動重送道具使用、煉金、製作或聊天等可能重複執行的操作；畫面將提示使用者先確認伺服器狀態。

## 功能分類

完整細項、條件及桌面版差異請閱讀 [電腦／手機功能對照](FEATURE_PARITY.md)。手機端的功能分區如下：

| 分區 | 範圍 |
| --- | --- |
| 帳號／角色 | 伺服器分流、登入選角、獨立連線、狀態與資源監控 |
| 戰鬥／隊伍 | AI 條件、補給、戰場陣形、手動戰鬥、組隊管理 |
| 移動／地圖／傳送 | 小地圖、位置、路線、傳送與場景資料 |
| 物品／製作／補給 | 背包、技能、煉金、材料、配方、收藏與排程 |
| 社交／紀錄／其他 | 聊天、組織、事件紀錄、經驗效率及偏好 |

資料尚未由遊戲伺服器確認時，核心應拒絕或暫停相關操作，例如未知位置、未學會的技能、未確認配方、未收到材料消耗結果等。不能用 UI 上存在某個按鈕，推論遊戲伺服器已接受該功能。

## v0.0.8｜正式 ARM64 原生核心打包

自 v0.0.8 起，手動／版本 Tag 完整 APK 工作流程改為 **先在隔離資料夾中把 `wlre/network/wire.py` 編譯成 `_wlre_wire_native.so`，再以既有固定 Debug 金鑰重新簽章**。正式儲存庫中的 Python 原始檔仍可用於回歸測試；原生替換只在 Android 打包暫存環境進行，桌面版不受影響。

正式 APK 上傳前必須同時通過 `NATIVE_WIRE_INFO.txt`（ARM64 ELF、Cython 模組位置、只有 shim bytecode）、`SIGNING_INFO.txt`（`Mode: persistent`、公開簽署者指紋 VERIFIED）、`PROTECTION_INFO.txt` 及 SHA256SUMS。任一項不通過就不提供新的 APK Artifact。其他 Python 位元碼仍可能被分析，並非全部原生化。

**更新注意**：如果手機目前安裝的是固定 Debug 簽章的舊版，同時 App package name 不變且系統判定 versionCode 可升級，v0.0.8 應能直接覆蓋更新；若安裝的是先前 Phase04 **臨時簽章的實驗 APK**，無法用固定簽章正式版直接覆蓋，且卸載可能刪除加密帳密／私有設定。請先確認簽署者，不要貿然卸載。

這次 CI 正式編譯、固定簽章與舊版原地升級仍須以 **v0.0.8 main 工作流程實際成功執行及手機更新結果**驗證，不能用先前實驗 APK 的成功紀錄代替。

## GitHub Actions｜節省額度的兩階段模式（2026-10-19）

因 GitHub-hosted Runner 免費分鐘數有限，已將日常 Python 測試與完整 Android 原生編譯分開。**一般 PR／main push 不再自動執行 Buildozer，也不會產生 APK。** 此模式不更改 Android 12（API 31）、ARM64-only、APK 版號、功能或既有固定簽章。

| 工作流程 | 觸發方式 | 執行項目 | APK 產物 |
| --- | --- | --- | --- |
| [Android fast checks (no APK)](../.github/workflows/android-smoke.yml) | 指定路徑的 PR、main push，或手動 | Python 3.11 回歸、語法、版本一致性、安全預檢、ARM64 配置檢查 | **無** |
| [Android ARM64 native phone APK (pinned signing)](../.github/workflows/android-apk.yml) | 在 **main 手動** Run workflow；或推送符合目前版本的 `vX.Y.Z` Tag | 相同測試 + 隔離 staging 內 Cython 3.0.12／NDK ARM64 原生 wire + pinned persistent 簽章 + SHA256 + 原生 ELF／shim／啟動畫面檢查 | `WLRe_LaLa-Android-vX.Y.Z-debug` |

### 需要新 APK 時：手動建置

1. 先確認 [快速測試 Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) 的最新 main 測試通過。
2. 打開 [Android phone APK (version tag)](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml)，按 **Run workflow**。
3. Branch 選擇 **main**，再按 **Run workflow**。其他分支會被版號檢查拒絕。
4. 等待成功後下載 `WLRe_LaLa-Android-v0.0.8-debug`（版本升級後名稱會隨版本變更）。ZIP 包含 APK、`SHA256SUMS.txt`、`SIGNING_INFO.txt`、`NATIVE_WIRE_INFO.txt`、`PRESPLASH_INFO.txt` 及 `PROTECTION_INFO.txt`。
5. 對照 `SIGNING_INFO.txt` 的 `Mode: persistent` 與 `Pinned public signer SHA256: VERIFIED`。不要把 PR 用的臨時簽章 APK 當作手機長期更新包。

需要發佈下一個新版本時，須先同步更新 `buildozer.spec` 與 `android_app/version.py`，然後才建立相符的 `vX.Y.Z` Tag；Tag 必須指向 main 歷史中的 Commit。**既有 GitHub Secret `ANDROID_DEBUG_KEYSTORE_BASE64` 和 Variable `ANDROID_EXPECTED_SIGNER_SHA256` 保持原樣，不重新產生或輸出私鑰。**沒有它們，完整建置會拒絕發佈，不會悄悄改用臨時簽章。

### 已有的最後一份自動 ARM64 主分支產物

- 歷史成功 Run：[39141939393](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39141939393)，Commit `dda1719`，Artifact 為 `Android-arm64-apk`，保存至 2026-10-26（台灣時間）。
- 此舊 Artifact 只在 GitHub 保存期限內可下載；**改成快速測試後，新 main/PR 的每次提交都不會再有 APK**。
- 當前不會自動進行 API 31～36 模擬器測試；ARM64 打包成功也不能代替真機遊戲登入與長時間背景驗收。

## 開發與測試

**主要程式**：`main.py`（Kivy 直式入口）；`android_app/`（UI、連線與服務）；`wlre/`（共用遊戲核心與資料）；`buildozer.spec`（Android 套件設定）。Android 使用本地 `wlre/` 副本，桌面專案的更改不會自動同步至手機。

日常快速 CI 使用 **Ubuntu 22.04、Python 3.11、Java 17**；只有手動／Tag APK 工作流程額外安裝 Buildozer 與 Android 工具鏈。本地 Linux 測試須具備系統相依套件及可用顯示器（或 Xvfb）：

```bash
python -m pip install -r requirements-dev.txt
xvfb-run -a python -m unittest discover -s tests -q
python -m compileall -q main.py android_app wlre tools
```

本地 ARM64 編譯（還需要 Android SDK／NDK 與 Buildozer 原生建置相依）：

```bash
python tools/android_native_wire.py stage --source . --output /tmp/wlre-android-native-release
(cd /tmp/wlre-android-native-release && buildozer -v android debug)
```

**修改 Android 版本**時，需同步調整 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION`；一般 `main` 更新**只執行快速測試，不再編譯 ARM64 APK**。要測試安裝包時從 main 手動執行 `android-apk.yml`；準備發布新版本時才建立相符的 Git Tag。不要把桌面版的 Nuitka、BAT、Tkinter 建置步驟混入 Android 專案。

## 驗收項目及限制

請區分快速測試與完整 APK 產物的 GitHub Actions 結果；只有手動／Tag 完整工作流程才能確認 ARM64 打包與固定簽章；歷史測試細節收錄於 [VALIDATION.md](VALIDATION.md)。目前**仍須 Android 真機確認**的項目包括：

- ARM64 手機的安裝、啟動、登入、選角，以及不同伺服器／分流下的狀態同步。
- 同時多帳號登入；中斷 A 帳號時不影響 B 帳號，網路切換與重新連線狀態是否正確。
- 懸浮小球授權、拖曳、展開、關閉、跨 App 顯示及權限撤銷後的回復。
- 自動戰鬥、徘徊、補給、煉金、製作與社交操作的實際伺服器回覆。
- 15／30／60 分鐘鎖屏與省電模式測試，包含斷線、重連、記憶體及裝置耗電觀察。

**請以實際封包或伺服器回應辨識成功，不以畫面顯示或背景服務程序存活代表所有功能正常。**

相關文件：[驗收規格](ACCEPTANCE.md) · [桌面／手機功能對照](FEATURE_PARITY.md) · [歷史驗證紀錄](VALIDATION.md) · [遷移說明](../MIGRATION.md)。
