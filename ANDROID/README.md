# 飄流 RE:LaLa｜Android 使用與技術指南

本文件集中說明 Android 客戶端的**操作流程、權限、背景機制、APK 建置及驗收限制**。首次安裝與下載入口請先閱讀 [專案首頁 README](../README.md)；功能逐項對照請參考 [FEATURE_PARITY.md](FEATURE_PARITY.md)。

**開發中版本：v0.0.7** ｜ **最低 Android 12（API 31）** ｜ **ARM64 手機與 x86_64 模擬器分別建置** ｜ **Debug 測試用途**

> 請勿安裝早期 v0.0.2／v0.0.3 的舊 APK：歷史紀錄曾確認 Keystore／PyJNIUS JNI 初始化崩潰。v0.0.7 新增的懸浮小球與遊戲自動化操作仍需真機驗收；「Actions 成功」不等於正式遊戲連線驗收。

## 操作流程

### 1. 安裝及開始登入

1. 在 [Smoke Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) 的**成功執行紀錄**下載 `Android-arm64-apk`，或於 [Phone APK Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) 取得指定版本的 ARM64 APK。
2. 解壓後確認 APK 與 `SHA256SUMS.txt`，在 ARM64 Android 12 以上手機安裝測試包。
3. 啟動程式、選擇地球／水星及分流，輸入帳號與密碼後登入。帳號驗證、角色清單與角色入場須等待伺服器實際回覆。
4. 可新增多個獨立連線；各帳號各自擁有停止旗標、指令佇列與狀態，不將一個帳號的操作轉送給另一個帳號。
5. 入場後在帳號卡片啟動／停止自動戰鬥或徘徊，也可開啟角色功能，操作戰場、地圖、補給、社交與製作等頁面。

停止某個帳號不等於停止其他帳號；「停止全部連線與服務」會關閉整個連線服務。若服務尚未就緒或已失去回應，UI 應顯示未知或失聯，不以先前快照冒充目前在線。

### 2. 前景通知及背景連線

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

## GitHub Actions 與下載檔案

本專案保留**開發測試**與**版本 Tag 建置**兩套流程；兩者都支援手動執行。**若需讓不同版本的 APK 簽章保持一致，必須依 [Android 固定簽章設定](SIGNING.md) 建立並設定 GitHub Secret `ANDROID_DEBUG_KEYSTORE_BASE64`。** 未設定前仍會編譯，但 Debug 簽章可能每次不同：

| 工作流程 | 觸發 | 執行範圍 | 下載項目 |
| --- | --- | --- | --- |
| [`android-smoke.yml`](../.github/workflows/android-smoke.yml) | `main` 指定程式碼有更新，或手動執行 | 版本欄位一致性、完整測試、Python 語法、獨立編譯 x86_64 與 ARM64，再測 API 31～36 模擬器啟動 | `Android-emulator-apk`、`Android-arm64-apk`；各有 APK + SHA256 |
| [`android-apk.yml`](../.github/workflows/android-apk.yml) | 推送 `vX.Y.Z` Git Tag，或從 `main` 手動執行 | 驗證 Tag／程式版號、測試、ARM64 編譯、SHA256 | `WLRe_LaLa-Android-vX.Y.Z-debug` |

### Smoke 產物（不帶版本號）

| Artifact | ZIP 內容 | 裝置 | 保存期限 |
| --- | --- | --- | --- |
| `Android-arm64-apk` | `WLRe_LaLa-Android-arm64-debug.apk`、`SHA256SUMS.txt`、`SIGNING_INFO.txt` | 一般 ARM64 Android 手機測試 | 7 天 |
| `Android-emulator-apk` | `WLRe_LaLa-Android-emulator-debug.apk`、`SHA256SUMS.txt`、`SIGNING_INFO.txt` | x86_64 Android 模擬器 | 7 天 |

Smoke 的模擬器測試矩陣為 API **31、32、33、34、35、36**，涵蓋 Android **12、12L、13、14、15、16**。測試會等待 UI／前景服務／Keystore 就緒、切至 Home 約 15 秒、鎖屏約 30 秒並返回畫面；**不使用真實遊戲帳密，也不驗證懸浮視窗的全部觸控行為**。

Smoke 的 ARM64 是另外一份 Debug APK 建置，**不是在 x86_64 模擬器上測 ARM64 ABI**；其存在不代表手機真實登入、戰鬥或長時間背景運行已通過。

### Phone APK 產物（帶版本號）

`android-apk.yml` 從 `buildozer.spec` 與 `android_app/version.py` 核對版號。自動觸發需要 Git Tag 為 `vX.Y.Z` 且符合原始碼的版本設定，Tag 的提交需在 `main` 歷史上。手動執行只允許從 `main` 建置。

例如 `v0.0.7` 的 Artifact 名稱為 `WLRe_LaLa-Android-v0.0.7-debug`，內含 `WLRe_LaLa-Android-v0.0.7-debug.apk`、`SHA256SUMS.txt` 及 `SIGNING_INFO.txt`，保存期限 14 天。它仍是 Debug 測試包，不是已完成真機驗收或商店簽署的正式發行包。

## 開發與測試

**主要程式**：`main.py`（Kivy 直式入口）；`android_app/`（UI、連線與服務）；`wlre/`（共用遊戲核心與資料）；`buildozer.spec`（Android 套件設定）。Android 使用本地 `wlre/` 副本，桌面專案的更改不會自動同步至手機。

CI 建置環境是 **Ubuntu 22.04、Python 3.11、Java 17、Buildozer**。本地 Linux 測試須具備系統相依套件及可用顯示器（或 Xvfb）：

```bash
python -m pip install -r requirements-dev.txt
xvfb-run -a python -m unittest discover -s tests -q
python -m compileall -q main.py android_app wlre tools
```

本地 ARM64 編譯（還需要 Android SDK／NDK 與 Buildozer 原生建置相依）：

```bash
buildozer -v android debug
```

**修改 Android 版本**時，需同步調整 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION`；一般 `main` 更新會跑 Smoke，但**不會自動觸發版本 APK 流程**。只有準備發布指定版本時才建立 Git Tag。不要把桌面版的 Nuitka、BAT、Tkinter 建置步驟混入 Android 專案。

## 驗收項目及限制

可從每次 [GitHub Actions](https://github.com/blesses0603/WLRe_lala_Android/actions) 的執行結果確認打包與模擬器測試；歷史測試細節收錄於 [VALIDATION.md](VALIDATION.md)。目前**仍須 Android 真機確認**的項目包括：

- ARM64 手機的安裝、啟動、登入、選角，以及不同伺服器／分流下的狀態同步。
- 同時多帳號登入；中斷 A 帳號時不影響 B 帳號，網路切換與重新連線狀態是否正確。
- 懸浮小球授權、拖曳、展開、關閉、跨 App 顯示及權限撤銷後的回復。
- 自動戰鬥、徘徊、補給、煉金、製作與社交操作的實際伺服器回覆。
- 15／30／60 分鐘鎖屏與省電模式測試，包含斷線、重連、記憶體及裝置耗電觀察。

**請以實際封包或伺服器回應辨識成功，不以畫面顯示或背景服務程序存活代表所有功能正常。**

相關文件：[驗收規格](ACCEPTANCE.md) · [桌面／手機功能對照](FEATURE_PARITY.md) · [歷史驗證紀錄](VALIDATION.md) · [遷移說明](../MIGRATION.md)。
