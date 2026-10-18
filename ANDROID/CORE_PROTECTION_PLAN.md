# Android 第 03 項｜敏感核心清單與 APK 封裝安全門檻

基準：`main` 0ee5ce1764a6bc9e551ba8b16695d76a87e1d478（第 02 項固定簽章已於 main 成功建置）。
本項是 **第 03 項：Cython 遷移前的敏感核心盤點、洩漏阻擋與 ARM64 封裝稽核**，不把第 04～05 項尚未完成的 ARM64 Cython 編譯冒充完成。

## 程式碼優先級

| 級別 | 程式路徑 | 風險／遷移注意 |
| --- | --- | --- |
| P0 | `android_app/vault.py` | Android Keystore AES-GCM 橋接、帳號密文讀寫；JNI 與加解密回歸必測 |
| P0 | `android_app/runtime.py` | UI／前景服務 Unix socket IPC 與控制命令；兩程序分離必測 |
| P0 | `android_app/sessions.py` | 角色登入、密碼生命週期、多連線隔離 |
| P0 | `wlre/network/client.py` | 連線與登入封包的敏感資料流 |
| P0 | `wlre/network/protocol.py` | 協定指令、登入編碼及服務端回應解碼 |
| P0 | `wlre/network/wire.py` | 封包位元組編碼／解碼；適合先做原生編譯相容性試點 |
| P1 | `wlre/services/battle/auto_battle.py` | 戰鬥決策；需封包 golden fixtures |
| P1 | `wlre/services/expedition.py` | 遠征邏輯；需伺服器 ACK 與多帳號測試 |

這是風險與工作排程清單，**不是**已經 Cython 保護的清單。首次原生試點建議 `wlre/network/wire.py`，需先確保封包 roundtrip、例外訊息及 Python 導入路徑一致。凡是實際改成 ARM64 `.so` 的核心，必須確認 APK 不再攜帶同名 `.py`、`.pyc`，不能僅以 APK 內存在其他 `.so` 為憑據。

## 本項立即生效的阻擋

1. 建置前固定 `android.minapi = 31`、`android.archs = arm64-v8a`、禁止備份，並查核 `main.py` 是否帶入已知私鑰格式。
2. APK 內層 `assets/private.tar` 及外層 ZIP 不得直接包含 LaLa `android_app/`、`wlre/` 或 `main.py` 的 `.py` 原始碼。
3. 拒絕非 ARM64 的 `lib/<ABI>/*.so`，拒絕私有 TAR 內的 symlink／hardlink 與目錄跳脫。
4. `PROTECTION_INFO.txt` 增列仍可提取的應用 `.pyc` 與 P0 `.pyc` 數量；數量是風險揭露，**不是保護成功數量**。
5. 原本的固定簽章 Secret／公開 SHA256 pin、APK 重簽與 SHA256SUMS 流程保持原樣；PR 使用臨時簽章。

## 第 04～05 項後續驗收門檻

- 使用 Android NDK 針對 ARM64 真正編譯指定核心，並在成品內驗證 **模組名稱、ABI、Python import 及原始／bytecode 缺席**；不能用 Linux `.so` 充當 Android 產物。
- 先驗證 `wire.py` 及其既有 Python tests 的原生／純 Python 行為一致，再擴及 P0／P1。
- 確認主 App 與前景服務皆能載入相同原生擴充套件；包含 Android Keystore JNI、登入及背景 IPC。
- 一般 PR 快速 Python 回歸先通過；實際涉及 Cython、NDK、APK 封裝的變更，需另外手動於 main 或發佈對應版本 Tag 執行 ARM64 APK 建置與產物檢查後才宣稱原生保護驗收完成。固定簽章僅在受信任的手動 main／Tag 工作流程驗證。

## 未解決風險

- `.pyc` 在 APK 中可分析，沒有因為去除 `.py` 而不可逆向。Cython 也只能增加成本。
- 已封裝第三方 Python 位元碼；此門檻只針對應用程式自身的原始碼與 ABI。
- 檔名與固定模式掃描無法檢查所有二進位硬編碼秘密、惡意 Runtime Hook、網路傳輸或真機動態攻擊；其他稽核項目仍須進行。
- 固定 Debug 金鑰維持測試用途，不是 Play 商店 Release 金鑰。

## 第 04 項準備（2026-10-19）

已在獨立分支 `security/android-phase04-cython-wire-pilot` 建立 `tools/android_cython_wire.py`（合成封包、主機 Cython/Python 行為對照）、`tests/test_android_cython_wire.py`（純 Python golden vectors）及 [PHASE04_CYTHON_PILOT.md](PHASE04_CYTHON_PILOT.md)（真正 Android ARM64 native 的驗收設計）。目前已新增 **隔離的 Android 原生建置 staging 工具、p4a CythonRecipe、APK ARM64 ELF 與核心來源殘留檢查**；標準 Buildozer 專案仍未啟用原生替換，尚未以 Android NDK 編譯出新 APK，也未進行 ARM64 APK／真機驗收。因 GitHub Actions 額度不足，本分支先不建立會觸發雲端快速測試的 PR，亦不合併 main。
