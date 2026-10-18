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
- `xvfb-run -a python -m unittest discover -s tests -q`、ARM64 Actions 全部成功，才可合併修改。

簽章設定見 [SIGNING.md](SIGNING.md)，Android 功能與實機驗收見 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 第 02 項：固定簽章保護（2026-10-18）

程式與 CI 已加入固定 Keystore 與 **另一個公開憑證指紋 Variable** 的交叉比對。推送 main／版本 Tag 的 APK 一律要求兩者存在並一致；PR 才容許臨時簽章（不使用私有 Secret）。兩次正式 main 建置的指紋一致性與真機覆蓋更新尚須實際設定與驗收，不可宣稱已完成。詳見 [SIGNING.md](SIGNING.md)。
