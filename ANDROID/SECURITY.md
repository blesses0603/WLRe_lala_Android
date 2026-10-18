# 飄流 RE:LaLa Android 防護狀態與安全發佈

這份說明專門區分「APK 簽章」、「帳密保護」和「原始碼保密」。三者不是同一件事。

## 已實作的防護

| 項目 | 狀態 | 說明 |
|---|---|---|
| APK 數位簽章 | 已有 | APK 簽署後驗證實際憑證指紋；Artifact 含 `SIGNING_INFO.txt`、`SHA256SUMS.txt` |
| 固定簽章防呆 | 已加入 | 版本 Tag／手動版本建置若缺少 GitHub Secret 就拒絕發佈 |
| ARM64 與 x86_64 測試 | 保留 | Smoke 可使用臨時 Debug 金鑰，但會標示 ephemeral、不能保證覆蓋舊版 |
| Android 帳密 | 已有 | Keystore AES-GCM 加密，專用私有目錄，不允許 Android 備份 |
| App 內部 IPC | 已有 | 私有 Unix socket，目錄 0700／Socket 0600 |
| 誤包私鑰掃描 | 已加入 | 建置前檢查敏感檔名與常見金鑰特徵，建置後檢查 APK ZIP 內容 |
| Python 原始碼混淆／Cython | **尚未實作** | 一般 Buildozer Debug APK 不能提供 Python 保密能力 |
| 反逆向與執行時防篡改 | **尚未實作** | 無法保證 APK 不受動態分析、Hook 或重新打包 |

**重要：目前 `WLRe_lala_Android` 是公開 GitHub 儲存庫。** 任何人都能讀取已公開的程式碼，所以僅增加 APK 混淆，不能保護已經公開的那份原始碼。將來若要讓敏感核心保密，應先評估改用私人來源；既有下載及 Fork 無法收回。

## 固定簽章一次性設定

1. 依照 [SIGNING.md](SIGNING.md) 於自己的可信任裝置產生簽章金鑰，勿貼到聊天或推上 GitHub。
2. 在 GitHub Actions Secrets 設定 `ANDROID_DEBUG_KEYSTORE_BASE64`。
3. 重新執行 Android Smoke；開啟手機 Artifact 的 `SIGNING_INFO.txt`，確認 `Mode: persistent`。
4. 下一次建置確認 `Certificate SHA256` 與上次相同，即可使用相同金鑰持續簽署測試 APK。

若手機已安裝其他臨時 Debug 簽章的舊版，**換新固定金鑰無法直接覆蓋**。卸載前先考慮 App 私有資料與帳號設定的備份。SHA256 檔案與 APK 名稱都無法繞過 Android 簽章比對。

## CI 安全掃描邊界

`tools/android_hardening.py preflight` 會檢查備份權限、發佈來源排除、專案中的危險金鑰檔名及常見 Token／私鑰特徵；只報告檔案位置，不印出秘密內容。

`tools/android_hardening.py report APK` 會檢查 APK ZIP 內高風險敏感檔名，並輸出 `PROTECTION_INFO.txt`，**誠實標註 Cython 混淆與 Runtime 反竄改未啟用**。

此檢查不保證找到所有憑證洩漏，也不檢查所有巢狀資源壓縮檔，更不等於防反編譯保證。

## 下一階段：Python 核心原生編譯

建議先把需要保密的模組改在私人來源管理，再選取少數相對獨立的封包解析／戰鬥計算程式，用 python-for-android 自訂 Cython recipe 分別為 ARM64／x86_64 交叉編譯。
驗證必須確認 APK **不再同時包含對應模組的 `.py` 原始檔**，並通過 Android 12～16 啟動測試與真機登入、背包、戰鬥、長時間連線。Cython 也不是不可逆的加密。

R8／ProGuard 只適用 Java／Kotlin，不能直接混淆 Python；Java 服務使用 PyJNIus 反射，混淆時必須保留對應 JNI 類名。

執行時簽名／完整性檢查可以提高二次打包難度，但在可控裝置上仍有可能被 Hook；不能聲稱防護百分之百。
