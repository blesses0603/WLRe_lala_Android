# 飄流 RE:LaLa Android｜安全稽核與防護現況

> 2026-10-18，第 01 項安全架構稽核；來源：`blesses0603/WLRe_lala_Android`，Android v0.0.7。安全現況與修復計畫須分開：本次沒有將 Python 變成不可反編譯的程式。

## 查核依據與範圍

- **程式碼**：`main.py`、`android_app/`、`wlre/`、`tools/android_hardening.py`、`buildozer.spec`、兩套 GitHub Actions、簽章與 Keystore 程式。
- **實際 APK**：GitHub Actions 成功執行紀錄 [39119900826](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39119900826) 的 `Android-arm64-apk`；僅代表該提交，不代表後續版本。
- **最新建置阻擋**：`cf75964` 的 [39124720231](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39124720231) 單元測試、語法檢查已通過，但 ARM64 工作整體失敗，未取得新 APK；須等後續 Actions 成功再把新建置視為驗收通過。
- **GitHub 權限**：稽核時 repository metadata 顯示 **Private**，不同於舊文件的「公開」說法。Private 不會收回過去已複製／下載的內容，具存取權的人仍可取得原始碼。
- **限制**：沒有實機解包執行、沒有動態 Hook 測試、沒有驗證正式遊戲連線；不是滲透測試。

## 實際 APK 基準證據

| 檢查項目 | 查核結果 |
| --- | --- |
| APK ABI | 僅找到 `lib/arm64-v8a/` 的 native libraries |
| 封裝方式 | `assets/private.tar` 實際是 gzip 壓縮的 tar payload |
| 應用 Python 原始檔 `.py` | APK 與 private.tar 內皆為 0 |
| Python 位元碼 `.pyc` | private.tar 內 **95 個**，包含 `android_app`、`wlre` 與進入點 |
| 原生 ARM64 `.so` | APK 內 **24 個**（Python/Android 執行依賴；**不代表** LaLa 核心已做 Cython） |
| Python 核心 Cython 保護 | **未啟用**；`.pyc` 仍可被抽取、分析，部分內容可能可反編譯 |
| 簽章 | `SIGNING_INFO.txt` 顯示 `Mode: ephemeral`，固定簽章尚未在這份 APK 驗證 |
| 直接以高風險檔名封裝的憑證 | 所查 APK 最外層及 private.tar 成員名稱未見高風險金鑰檔 |
| 防篡改／反 Hook | 尚未實作；不聲稱具備防護 |

## 已有防護

1. Android Keystore AES-256-GCM 儲存使用者選擇保存的帳密，且 `android.allow_backup = False`；不等於記憶體或輸入過程零洩漏。
2. 前景服務與 App 使用私有 Unix socket IPC，設定了路徑權限；仍須靠 Android 沙盒與裝置安全。
3. APK 簽章驗證、簽章指紋與 SHA256 產物已納入建置；**SHA256 清單不等於不可竄改機制**。
4. 建置前會掃描敏感檔名與部分固定格式的憑證特徵。新版建置後掃描除了 APK ZIP 外層，也檢查 `assets/private.tar` 內層成員名稱；新增 `PROTECTION_INFO.txt` 位元碼曝露數量。
5. Debug APK 不是正式 Release 發佈；是否可用同簽章覆蓋，需確認 `SIGNING_INFO.txt` 的 `Mode: persistent` 及憑證指紋一致。

## 尚未完成的保護

| 風險 | 優先處理項目 |
| --- | --- |
| 固定簽章未驗證（基準 APK 為 ephemeral） | 第 02 項：CI 已加入固定憑證 SHA256 pin；仍須使用者設定 Secret + Variable、兩次 main APK 比對及真機更新驗收 |
| 多個 Python `.pyc` 可分析 | 第 03～05 項：敏感核心選擇及 ARM64 Cython 編譯 |
| 潛在憑證藏在其他巢狀 ZIP、二進位及動態記憶體 | 第 06、08 項：分層檢查、帳密與 IPC 安全檢視 |
| 沒有執行時反篡改 | 第 07 項：驗證可行性及錯誤處理 |
| Android 真機恢復、長時間背景行為 | 第 10 項：真機驗收 |

目前工具仍**不**能掃描所有巢狀 ZIP 的內容或偵測所有硬編碼秘密，不得將「PASSED」解讀為全面安全；也不能只靠 ProGuard/R8 保護 Python。Cython 提高逆向成本，不能保證絕對不可分析。

### 驗證方式

- `python tools/android_hardening.py preflight`：掃描建置設定與原始碼敏感檔名／常見特徵。
- `python tools/android_hardening.py report path/to/app.apk`：檢查 ZIP 與內嵌 `assets/private.tar` 成員名稱，產生 `PROTECTION_INFO.txt`。
- `python -m unittest tests.test_android_hardening -v`：驗證原始碼邊界、巢狀金鑰與位元碼計數。
- 一般 PR：`xvfb-run -a python -m unittest discover -s tests -q` 與 Python／設定安全預檢成功才可合併；PR 快速 CI **不再編譯 APK**。涉及 Android 原生、打包或實際封裝安全的變更，仍須安排手動／Tag 完整 ARM64 APK 驗證，不可把快速測試當成實際 APK 成功。

簽章設定見 [SIGNING.md](SIGNING.md)，Android 功能與實機驗收見 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 第 02 項：固定簽章保護（2026-10-18）

程式與 CI 已加入固定 Keystore 與 **另一個公開憑證指紋 Variable** 的交叉比對。**在 main 手動執行或推送版本 Tag 時**的 APK 一律要求兩者存在並一致；PR 日常不再產 APK（不使用私有 Secret）。兩次正式 main 建置的指紋一致性與真機覆蓋更新尚須實際設定與驗收，不可宣稱已完成。詳見 [SIGNING.md](SIGNING.md)。

## 第 03 項：核心風險分級與封裝安全門檻（2026-10-18）

此項聚焦 **敏感 Python 模組盤點、Android 12+/ARM64 編譯組態鎖定、APK 應用原始碼洩漏阻擋，以及既有位元碼的曝露紀錄**。詳細的 P0／P1 模組清單與第 04～05 項 Cython 遷移門檻請參閱 [CORE_PROTECTION_PLAN.md](CORE_PROTECTION_PLAN.md)。

- `preflight` 拒絕降低 Android min API、增加非 ARM64 ABI，並額外掃描進入點 `main.py` 的已知私鑰格式。
- `report` 對 APK 外層與 `assets/private.tar` 內層拒絕 `android_app/`、`wlre/`、`main.py` 的未編譯 `.py`，同時拒絕巢狀 TAR 連結、目錄跳脫及非 ARM64 native libraries。
- `PROTECTION_INFO.txt` 明列 App 與高風險核心仍曝露的 `.pyc` 數量。**本階段尚未加入 Cython，也無法防止 .pyc 逆向分析。**
- 沿用第 02 項已驗證的 GitHub Repository Secret `ANDROID_DEBUG_KEYSTORE_BASE64` 與 Variable `ANDROID_EXPECTED_SIGNER_SHA256`，不更換／重生金鑰；只有受信任 main／Tag 建置能使用固定簽章。

第 03 項的通過條件是 Python 回歸、ARM64 APK 編譯與安全稽核全部成功。這是實際阻擋意外暴露的封裝加固，不是完成原生程式防逆向；第 04～05 項仍需真正的 Android NDK／Cython 編譯及真機導入驗證。

## 2026-10-19：降低 Actions 消耗，不降低發行安全門檻

`android-smoke.yml` 改為 PR／main Python 回歸、語法及安全預檢；不下載私鑰、不執行 Buildozer、不上傳 APK。`android-apk.yml` 維持僅在 main 手動執行或推送符合程式版號的 `vX.Y.Z` Tag 才完整打包，既有固定簽章指紋鎖定、重簽、SHA256、啟動畫面與 APK 成員稽核維持不變。最新既有的主分支完整成功證據：[Run 39141939393](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39141939393)（commit `dda1719`）。


## 第 06 項：巢狀封裝、帳密及 IPC 加固（2026-10-19）

**實作**：

- tools/android_archive_audit.py：在既有 Phase03 檔名／ARM64 檢查以外，受限遞迴掃描 APK ZIP、p4a private.tar、libpybundle.so TAR、內嵌 ZIP/TAR；拒絕危險路徑、連結、重複成員、已知私鑰樣式和超過深度/大小限制的巢狀封裝。掃描前不會將成員解開到磁碟，錯誤不顯示匹配到的機密內容。
- android_app/runtime.py：相同 Android UID 的 AF_UNIX SO_PEERCRED 驗證；最大 1MiB、完整換行、JSON 物件、重複 key／非法 UTF-8／NaN 拒絕，回覆沿用同一格式。
- android_app/vault.py：帳號密文原格式／Android Keystore alias 不變；讀檔 O_NOFOLLOW、普通檔檢驗，寫入 O_EXCL|O_NOFOLLOW、0600 與目錄 0700 保護。
- tools/android_hardening.py 的 APK report 會執行新增巢狀驗證，更新 PROTECTION_INFO.txt，八核心狀態以 PHASE05_ALL_CORES_INFO.txt 獨立稽核為準。
- 新增 tests/test_android_phase06_security.py 與更新既有回歸；Phase06 PR 快速 CI #39269444172：**290 tests OK**，Python 預檢通過；屬主機/CI 功能驗收，**非**新正式 APK 編譯或真機證據。

**邊界**：不能保證偵測所有金鑰，未遍歷未知加密封裝及所有大型二進位內容；靜態檢查也不阻擋運行中的 hook/記憶體攻擊。SO_PEERCRED 驗證相同 UID，不等於防止同 UID 的惡意程式碼。真機登入、Keystore 資料搬移／覆蓋更新仍以發行後安裝驗收為準。完整測項見 [PHASE06_SECURITY.md](PHASE06_SECURITY.md)。


## 第 07 項：安裝簽署憑證完整性與雙程序入口驗證（2026-10-20）

- Java RuntimeIntegrity 使用 Android PackageManager SigningInfo 驗證已安裝的 package 與**當前唯一簽署憑證** SHA-256 是否吻合固定簽章的公開憑證 pin。Python Activity、Android Java ConnectionService、獨立 Python foreground service 在處理帳號、建立連線前分別驗證，失敗則中止操作，不印出私有資料或原始例外。
- 正式 main/tag APK 工作流將公開指紋寫到隔離 stage Java 原始檔（原始 repo 保留 placeholder），**私鑰依然只進入原本簽署步驟**；即使編譯成功，也必須在最終 APK DEX 找到該 public pin 且 apksigner 確認簽署者身份，否則不上傳。
- Python 與 Java 測試（含 JVM 執行模擬簽署者不符、多簽署者、錯誤 package、SDK 不符與 JNI 異常）已加入 PR 快速 CI；第 07 項程式測試 Run #39334752525：**300 tests OK**。
- **尚未聲稱** Android 正式固定簽章新版 APK 及 Android 12+ ARM64 真機重新打包防護測試成功。未經固定簽章發行程序 pin 的本機測試 APK 預設拒絕進入敏感功能。
- 這是客户端 defense-in-depth，**不是 Play Integrity/伺服器驗證或不可繞過的反 Hook 技術**。客戶端能被具備修改能力的攻擊者 patch，Root/Hook 威脅仍未根除。詳見 [PHASE07_INTEGRITY.md](PHASE07_INTEGRITY.md)。


## 第 08 項：帳密參照縮短與診斷隱私（2026-10-20）

- 已保存帳號清單僅在長期 UI State 保留帳號/伺服器，按需解密所選帳號，保存/刪除仍使用既有 Android Keystore AES-GCM 與相同資料格式；不再把全部明文密碼長期保留於 \`self.saved_accounts\`。
- Android UI→service 的 start 命令和 service 端收到的 start 命令，在成功/失敗後移除其 mutable request 內的 password 欄位，降低佇列裡長時間保留密碼參照的風險。
- Android smoke 測試將下載用診斷改成**固定事件/錯誤碼/計數摘要**。原始 \`logcat\` 與 \`dumpsys\` 內容不會寫入 GitHub Actions 產物或失敗 console；須在可信任裝置上另外以明確同意收集詳細日誌。
- 無法承諾 Python/Kivy/JNI 字串在記憶體真正零化，亦無法保護已遭 Root、Hook 或 OS 層級入侵的手機；正式 ARM64 APK / Android 12+ 真機完整回歸仍是後續發布驗收。
- 依照 [PHASE08_CREDENTIAL_PRIVACY.md](PHASE08_CREDENTIAL_PRIVACY.md) 的單元與 Kivy 回歸測試紀錄驗收；日常 PR 不觸發完整 APK。
