# 第 05 項｜P0/P1 漸進原生化：第一批 Android 帳號保管庫

基準：Android v0.0.8，PR #8 合併後 main c4dfbb8c0e06e8b14186c86f0f286e9863bd3e95。
本次僅選擇 P0 android_app/vault.py 為第一批，不重做第 04 項已完成的 wlre/network/wire.py。

## 敏感模組分批

| 級別 | 核心 | 狀態 |
| --- | --- | --- |
| P0 | wlre/network/wire.py | Phase04 已保護，完整保留 |
| P0 | android_app/vault.py | Phase05 第一批，Android Keystore/AES-GCM 帳密保管庫 |
| P0 | android_app/runtime.py | 後續，需 IPC 及服務生命週期測試 |
| P0 | android_app/sessions.py | 後續，需多帳號、登入與憑證生命週期測試 |
| P0 | wlre/network/client.py | 後續，需多連線及登入協定回歸 |
| P0 | wlre/network/protocol.py | 後續，需封包 golden vectors |
| P1 | wlre/services/battle/auto_battle.py | 後續，需戰鬥封包 fixtures |
| P1 | wlre/services/expedition.py | 後續，需 ACK 與遠征狀態驗證 |

## 本批實作與邊界

1. 正常 checkout 仍保留 Python 版 vault、wire、預設 buildozer.spec，方便持續開發。
2. tools/android_native_vault.py 先利用既有 Phase04 wire stage，僅在獨立暫存目錄把 vault.py 實作搬進 p4a-recipes/lalavault/src/_wlre_vault_native.pyx，App 改為只導出 AndroidCipher / AccountVault 的 shim。
3. 加入 lalavault 原生 recipe；保持 wlre/network/wire.py 不改，也不更換既有原生 wire recipe。
4. 原生 APK 稽核必須同時通過 Phase04 wire 驗證與 Phase05 vault 驗證：AArch64 ELF、p4a site-packages、準確 shim bytecode、原 vault 實作來源/bytecode 0 洩漏。
5. 完全不接觸固定簽章 Secrets、Android Keystore 金鑰、key alias、密碼格式及儲存路徑。
6. Cython 僅提高靜態逆向成本，不能保證不可逆向，也不是新的資料加密方式。

## 測試命令

    python -m unittest tests.test_android_native_vault -v
    python tools/android_native_vault.py stage --source . --output /tmp/lalavault-phase05
    cd /tmp/lalavault-phase05 && buildozer -v android debug

Android p4a hostpython3.14 建置完成後，可使用原 repo 工具驗證 APK：

    python tools/android_native_vault.py report-apk /tmp/lalavault-phase05/bin/APP.apk --pyc-python /tmp/lalavault-phase05/.buildozer/android/platform/build-arm64-v8a/build/other_builds/hostpython3/desktop/hostpython3/native-build/root/usr/local/bin/python3.14

隔離試驗 workflow：.github/workflows/android-native-vault.yml。
本批實驗 APK 仍為非固定簽章 Debug APK，不得拿來覆蓋既有固定簽章安裝。

## 合併、發布和後續模組閘門

- PR 快速 Python 回歸測試與安全預檢通過。
- 隔離的 Phase05 ARM64 APK 真正編譯，wire/vault 雙原生模組稽核通過，無原實作來源洩漏。
- Android 12+ ARM64 真機 Keystore：建立金鑰、儲存/讀取帳號、重啟後讀取、刪除和錯誤密文拒絕；前景服務 IPC、背景登入亦需驗證。
- 以上全部成功後，另行接入正式 main 固定簽章 APK；不能把實驗建置當正式升級。
- Phase05 其他 P0/P1 清單尚未完成，必須逐批驗收。
