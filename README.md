# 飄流 RE:LaLa｜Android 客戶端

**Android 直式觸控客戶端（開發測試版）**。此專案獨立於 [WLRe_lala Windows／macOS 桌面版](https://github.com/blesses0603/WLRe_lala)，使用自己的 `main` 分支、版本號及 GitHub Actions。遊戲通訊與功能核心由本專案的 `wlre/` 提供，不需在手機執行桌面程式。

> **目前原始碼版本：v0.0.7** ｜ **最低系統：Android 12（API 31）** ｜ **手機架構：ARM64（arm64-v8a）** ｜ **產物：Debug 測試 APK**
>
> 「程式已有功能」不代表「真實伺服器及所有手機已驗收」。請用測試帳號先行確認；任何 APK 都以其所在 Actions 執行頁的結果為準。

## 目錄

- [下載與安裝](#下載與安裝)
- [主要功能](#主要功能)
- [GitHub Actions 與 APK 區別](#github-actions-與-apk-區別)
- [權限、背景與懸浮小球](#權限背景與懸浮小球)
- [開發、測試與版本發布](#開發測試與版本發布)
- [專案結構與文件](#專案結構與文件)
- [已知限制與常見問題](#已知限制與常見問題)

## 下載與安裝

**想在 ARM64 手機上立即試用目前 `main` 的程式，請先選 Smoke 流程的 `Android-arm64-apk`。** 不要把 x86_64 模擬器 APK 裝到 ARM64 手機。

| 需求 | 前往 Actions | 下載的 Artifact | ZIP 內的 APK |
| --- | --- | --- | --- |
| **ARM64 手機測試** | [Android emulator startup smoke](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) | `Android-arm64-apk` | `WLRe_LaLa-Android-arm64-debug.apk` |
| Android 12～16 模擬器測試 | [Android emulator startup smoke](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) | `Android-emulator-apk` | `WLRe_LaLa-Android-emulator-debug.apk` |
| 指定版本的 ARM64 測試包 | [Android phone APK (version tag)](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) | `WLRe_LaLa-Android-vX.Y.Z-debug` | `WLRe_LaLa-Android-vX.Y.Z-debug.apk` |

**安裝步驟**

1. 點進對應的 Actions，選擇**最新且成功完成、對應你想測試之提交**的執行紀錄。若執行尚未結束或建置失敗，Artifact 可能不存在。
2. 在執行頁下方的 **Artifacts** 下載 ZIP，解壓縮後取得 APK 和 `SHA256SUMS.txt`。
3. 確認手機為 Android 12 以上、CPU 支援 ARM64；使用手機檔案管理工具開啟 APK，依系統提示允許該來源安裝應用程式。
4. 開啟 App，選擇伺服器／分流，輸入帳密並登入，等待伺服器回應後再選取角色。角色登入後，才啟用自動戰鬥或自動徘徊。
5. 需要懸浮小球時，再到「服務與資源」手動開啟並授權，**不是安裝後強制顯示**。

`SHA256SUMS.txt` 可用於檢查下載的 APK 是否損壞。在 Linux／macOS 可於解壓後目錄使用 `sha256sum -c SHA256SUMS.txt`（macOS 若未安裝 `sha256sum`，可使用 `shasum -a 256 <APK檔名>` 與清單比對）；Windows 可使用 PowerShell `Get-FileHash <APK檔名> -Algorithm SHA256` 比對。

> **更新或重裝注意**：CI Debug APK 可能使用不同簽章，無法直接覆蓋舊 APK。解除安裝可能同時刪除 App 私有設定與 Keystore 相關密文；先確認所需資料，切勿把解除安裝當成無損升級。

## 主要功能

| 類別 | 目前已整合的操作入口 |
| --- | --- |
| **帳號與角色** | 地球／水星伺服器及分流選擇、多帳號獨立連線、登入／選角／個別停止、角色資料與資源監控 |
| **戰鬥與 AI** | 自動戰鬥、自動徘徊、角色／夥伴 AI 規則、補給設定、戰場陣形與手動戰鬥操作 |
| **地圖與移動** | 小地圖、角色位置、移動與停止、傳送／場景資料；依已同步位置和地圖資料判斷可用性 |
| **物品與製作** | 背包、已確認技能、HP／SP 補給、煉金、製作配方、收藏與製作排程 |
| **社交與紀錄** | 聊天、組隊、組織相關操作、事件紀錄、經驗效率與升級預估 |
| **Android 專用** | 獨立背景連線服務、前景通知、Keystore 加密保存帳密、沿用 App ICON 的懸浮小球；展開可查看角色概況、HP／SP、AI 與補給狀態（需授權） |

以上表示**程式與操作介面已整合**，不表示所有遊戲行為都已在真實伺服器成功驗收。詳細功能、不可用條件及與桌面版的差異，請看 [電腦／手機功能對照](ANDROID/FEATURE_PARITY.md)。

## GitHub Actions 與 APK 區別

| 工作流程 | 什麼時候執行 | 產生什麼 | 保留時間 |
| --- | --- | --- | --- |
| [`android-smoke.yml`](.github/workflows/android-smoke.yml) | `main` 指定程式檔有更新，或手動執行 | **x86_64 模擬器 APK** ＋ **ARM64 手機 Debug APK** ＋ SHA256；另有 Android API 31～36 啟動診斷 | APK Artifacts：7 天 |
| [`android-apk.yml`](.github/workflows/android-apk.yml) | 推送符合版本規則的 Git Tag（`vX.Y.Z`），或從 `main` 手動執行 | **帶版本名稱的 ARM64 Debug APK** ＋ SHA256 | 14 天 |

- **Smoke**：驗證版本設定一致、執行單元測試與 Python 語法檢查，獨立建置 ARM64／x86_64。模擬器測試會檢查 UI／前景服務／Keystore 就緒、切回 Home、短暫鎖屏及返回畫面。
- **Phone APK**：使用版本 Tag 與原始碼版號檢查；一般 `main` 提交**不會**觸發這個工作流程。
- Smoke 的 **Artifact 及 APK 名稱不帶版本號**；App 的內部版本仍來自 `buildozer.spec` 與 `android_app/version.py`。
- GitHub Actions 頁面可能同時顯示歷史失敗與最新成功紀錄，應選取**指定執行的結論**，不要只看工作流程標題。模擬器啟動成功不等於真機登入或懸浮小球操作已驗收。

## 權限、背景與懸浮小球

首次啟動可能要求 Android 13 以上的通知權限，以配合前景服務通知。使用懸浮小球時，在「服務與資源」點「開啟懸浮小球」，再由系統設定允許**顯示在其他應用程式上層**。小球可拖曳、點開查看遮罩帳號與連線／AI 狀態，並可隱藏；**隱藏小球不會主動結束背景遊戲連線**。

前景服務、喚醒鎖與 TCP keepalive 有助於背景連線，但**不能防止 Android 強制停止、關閉通知、撤銷懸浮權限或廠商省電限制**。在 Android 15 適用條件下，`dataSync` 前景服務有每 24 小時累計約 6 小時的背景執行時限；本專案不承諾永久在線。

帳密僅在使用者勾選保存時使用 Android Keystore AES-256-GCM 加密保存於 App 私有目錄。不要將 APK／帳號資料視為可跨重新安裝或換機直接移轉。完整操作與安全說明見 [Android 使用與技術指南](ANDROID/README.md)。

## 開發、測試與版本發布

本專案入口是 `main.py`（Kivy），打包使用 `buildozer.spec`，主程式需要 Python 遊戲通訊核心 `wlre/`。開發 CI 使用 **Python 3.11、JDK 17、Ubuntu 22.04、Buildozer**。

在具備相依套件與桌面顯示器的 Linux 開發環境，可執行：

```bash
python -m pip install -r requirements-dev.txt
xvfb-run -a python -m unittest discover -s tests -q
python -m compileall -q main.py android_app wlre tools
```

本地編譯 ARM64 Debug APK（需先安裝 Android SDK／NDK 及 Buildozer 所需 Linux 建置相依）：

```bash
buildozer -v android debug
```

**發佈下一個版號**：先同步修改 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION`，提交至 `main` 並確認測試，再建立與該版本一致、指向 `main` 提交的 Git Tag，例如：

```bash
git tag v0.0.8
git push origin v0.0.8
```

以上指令**只是未來版本的範例**；目前不需要為了測試 Smoke ARM64 APK 而建立任何 Tag。專案 Android 版號與桌面版本號獨立。

## 專案結構與文件

| 路徑 | 職責 |
| --- | --- |
| `main.py` | Android Kivy 啟動入口 |
| `android_app/app.py`、`android_app/pages/` | 直式主畫面與各功能頁 |
| `android_app/sessions.py`、`android_app/runtime.py`、`android_app/service.py` | 獨立連線、私有 IPC、前景服務 |
| `android_app/java/`、`android_app/overlay_state.py` | 前景通知、懸浮球與遮罩後的狀態摘要 |
| `android_app/vault.py`、`android_app/preferences.py` | 加密帳密及偏好設定 |
| `wlre/` | 網路封包、戰鬥、社交、地圖、物品、儲存與資源 |
| `buildozer.spec`、`.github/workflows/` | APK 設定與兩種 GitHub Actions |
| `tests/`、`tools/` | 回歸測試、版本檢查與模擬器啟動測試 |

**延伸文件**：[Android 使用與技術指南](ANDROID/README.md) · [完整功能對照](ANDROID/FEATURE_PARITY.md) · [實機驗收項目](ANDROID/ACCEPTANCE.md) · [歷史驗證紀錄](ANDROID/VALIDATION.md) · [從桌面專案拆分說明](MIGRATION.md)。

## 已知限制與常見問題

- **Artifacts 找不到**：先確認該次 Workflow 已成功完成、沒有過期；Smoke 的 ARM64 與模擬器 APK 是**不同** Artifacts。
- **安裝顯示不相容**：確認 Android 12 以上，手機選 `Android-arm64-apk`，勿選 x86_64 模擬器包。
- **安裝顯示簽章衝突**：不同 CI Debug 簽章可能不能覆蓋舊版，請先評估 App 資料風險。
- **懸浮球沒有出現**：先啟動背景服務，在系統特殊權限授權，返回 App 後再次檢查「服務與資源」開關。
- **背景斷線／鎖屏異常**：Android 的省電、網路與前景服務時限都可能影響連線；不能只憑通知仍顯示就判定遊戲在線。
- **舊 APK**：v0.0.2／v0.0.3 曾有 Keystore JNI 啟動崩潰紀錄，不建議繼續使用。

請以 [GitHub Actions](https://github.com/blesses0603/WLRe_lala_Android/actions) 的個別執行結果與 [驗證紀錄](ANDROID/VALIDATION.md) 判斷測試範圍。更完整的操作及驗收說明請參閱 [Android 使用與技術指南](ANDROID/README.md)。
