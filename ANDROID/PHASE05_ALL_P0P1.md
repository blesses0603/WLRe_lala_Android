# Android 第 05 項｜P0/P1 全部核心原生化整合紀錄

基準：v0.0.8，main c4dfbb8c0e06e8b14186c86f0f286e9863bd3e95。
使用者已調整驗收順序：**先完成全部 P0/P1 程式與測試，再只建置一次整合實驗 APK，最後實機驗收**。
此文件不宣稱尚未執行的 Android 裝置測試成功。

## 核心覆蓋（8/8 已有原生建置接線，≠ 8/8 ARM64 實測通過）

| 風險 | 原模組 | 編譯擴充套件 | 配置 |
| --- | --- | --- | --- |
| P0 | wlre/network/wire.py | _wlre_wire_native | Phase04 現有 lalawire recipe，不重做 |
| P0 | android_app/vault.py | _wlre_vault_native | Phase05 lalavault recipe |
| P0 | android_app/runtime.py | _wlre_runtime_native | Phase05 lalaruntime recipe |
| P0 | android_app/sessions.py | _wlre_sessions_native | Phase05 lalasessions recipe |
| P0 | wlre/network/client.py | _wlre_client_native | Phase05 lalaclient recipe |
| P0 | wlre/network/protocol.py | _wlre_protocol_native | Phase05 lalaprotocol recipe |
| P1 | wlre/services/battle/auto_battle.py | _wlre_auto_battle_native | Phase05 lalaautobattle recipe |
| P1 | wlre/services/expedition.py | _wlre_expedition_native | Phase05 lalaexpedition recipe |

## 隔離打包

- 正式 checkout 完全保留原有 Python 程式及第 04 項的 wire 原生化，日常開發與修 BUG 無須重建 APK。
- tools/android_native_cores.py stage 在全新的暫存資料夾依序使用 Phase04 wire、Phase05 vault 的既有隔離 staging，然後加入其餘六個敏感核心，**不修改正式 main.py 或 buildozer.spec**。
- 每一個原 Python 實作會成為相應的 .pyx 原生建置輸入，原路徑留一個只有原生匯入與公開/私有屬性轉發的兼容 shim。
- 由實際 python-for-android SDK/NDK 編譯 ARM64；驗證器要求八個核心全部以可導入的 ARM64 ELF 放在 libpybundle.so site-packages，shim .pyc 和目標 hostpython3.14 exact match；任何原始實作、重複 extension 或不符合 ABI 一律停止，不上傳成品。
- 暫時 Debug 簽章的實驗 APK 不能覆蓋目前使用者原有固定簽章版本；此流程不授權讀取 GitHub 固定簽章 Secrets。
- Native core module globals reside in the compiled module. Python monkeypatch or reflection semantics may differ from source modules; compatibility is an explicit acceptance risk to test on device, not an assumption.

## 驗收順序

- [x] 六個新增核心 Linux 主機 Cython 編譯完成，Actions #39261841574 Success。
- [x] Python 274 項回歸與 APK 模擬封裝/ABI 篡改拒絕，Actions #39262125426 Success。
- [x] 全部八核心 NDK ARM64 **實驗 APK**、wire/vault/all cores 原生稽核、來源洩漏阻擋、SHA256，Actions #39262487138 Success。
- [x] 最新 PR 提交的快速安全回歸，Actions #39262495867 Success。
- [x] 使用者於 2026-10-19 回報「好了」；此為使用者確認驗收完成，**沒有逐項測試日誌**，不能推論每個子功能均有裝置端測試證據。
- [x] 正式固定簽章流程接入八核心 stage 及 wire/vault/all-core 三重 fail-closed APK 稽核。
- [ ] **正式固定簽章八核心 APK**：須於合併後由 main 手動觸發建置、比對簽章與完整更新測試；實驗簽章 APK 不可作舊版覆蓋升級證據。

目前不覆蓋現有 Android 客戶端、不新建/更換簽章、不改變 Python 專案、Android 12+ 或 arm64-v8a 的規則。
Cython 僅增加逆向門檻，不可聲稱不可破解；敏感金鑰仍應交給 Android Keystore 持有。

## 驗證命令（在有相依套件的環境）

    python -m unittest discover -s tests -q
    python tools/android_native_cores.py host-compile
    python tools/android_native_cores.py stage --source . --output /tmp/lalaphase05-all
    # 下一階段 Android NDK 建置於 /tmp/lalaphase05-all
    python tools/android_native_cores.py report-apk /tmp/lalaphase05-all/bin/APP.apk --pyc-python /tmp/lalaphase05-all/.buildozer/android/platform/build-arm64-v8a/build/other_builds/hostpython3/desktop/hostpython3/native-build/root/usr/local/bin/python3.14

PR #9 合併前須通過新增的發行流程回歸測試；正式八核心固定簽章 APK 與更新測試需以合併後新 Actions Run 為準，不能使用前期實驗版結果代替。
