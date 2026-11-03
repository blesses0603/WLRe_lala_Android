# 版本紀錄

## 0.1.0 開發整合版（尚未正式發布）

- 補上 `tpk_ar 0.2.4` 的固定來源與 SHA-256 本機 recipe，從原始碼安裝純 Python TPK 解析器及授權檔，排除 APK 建置 binary-only 安裝找不到 wheel 的問題；完整 APK 仍待 CI 驗證。

- 修復 LZ4 編譯時 `setuptools_scm` 找不到 `vcs_versioning`：透過 p4a 的 hostpython 建置相依安裝版本工具，避免只安裝到 Android 目標環境；完整 APK 編譯仍待 CI 驗證。

- 同步桌面 v7.0.1 與 PR #65 遊戲核心、動態官方資料及 SQLite。
- 新增 Android NPC、帳篷、儲藏存取、福利魔方及自動接續入口。
- 保留副本／協力手動開始、Android 背景服務、Keystore、固定簽章與八核心原生稽核。
- APK 安裝、ARM64 執行與正式服逐項驗收尚待完成。

## 0.0.8

本次修改前 Android main 的版本；既有發布與歷史驗收紀錄請參閱 ANDROID/ 下原始文件。
