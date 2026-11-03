# Android 與桌面功能同步整合（2026-11-03）

本次從 Android main `e1767b33ac4e83dc60bd34539c3d2889380b861d`（v0.0.8）建立獨立分支，預計 Android v0.1.0。桌面 main 為 v7.0.1，並整合尚未合併的 PR #65 核心。精確來源以 DESKTOP_SOURCE_LOCK.json 為準。

## 程式整合

- 同步 core／network／services／storage，包含動態官方 Runtime、SQLite、資料庫歷史相容、實體門、NPC、製作與共用物品預留。
- 手機 IPC 明確新增 NPC、帳篷、儲藏、魔方及自動接續命令和必要狀態。不提供原始封包入口、商店交易或付費寶箱自動購買。
- 新增 NPC、儲藏存取與福利頁；概況加入帳篷與自動接續控制。NPC 選項或商店到達時可切至 NPC 頁，不代選答案。
- 移除操作後重複確認；公開副本選擇後直接加入，私人房間保留密碼輸入。副本／協力開始及準備仍由使用者操作。
- 服務先準備並驗證官方資料；介面從共用私人快取獨立啟用 Runtime。兩端資料身分不符時不開放操作。
- SQLite 初始資料庫由建置流程依鎖定桌面提交下載並校驗；APK 包含完整資料庫，使用者不需自行下載桌面檔案。

## Android 必要適配

1. 遠征拆分後，八核心原生編譯目標由 expedition.py 改為 expedition/manager.py；其內部匯入使用絕對路徑，維持原生模組可匯入性。
2. 官方 Manifest 解析所需函式從桌面工具抽出至可打包的 manifest_parser.py，避免執行期依賴被 APK 排除的 tools。
3. 保留 Android 原有 instance_members 指令與診斷匯入 API；加上未知副本查詢參數拒絕。
4. 製作被共用協調器暫停時同步狀態原因，避免手機顯示過期的等待訊息。
5. 新增固定版本 UnityPy TextAsset reader、LZ4、Brotli、SQLite、TLS／CA 與 LZMA 建置接線。UnityPy 使用上游純 Python 型別樹 fallback；不複製主機 ELF 或 FMOD，既有圖片仍讀取資料庫。

## 驗收界線

- 原始碼回歸、主機 Cython 編譯、APK ARM64 編譯、安裝更新、手機 UI／背景服務與正式服操作為不同驗收項目。
- 沒有正式服帳號或手機操作結果時，不宣稱 NPC、扣料、儲藏、魔方領取或鎖屏背景流程已實測成功。
- 本地 Unix socket 不可用的環境會明確跳過相關實際往返測試；CI 具備此能力時仍執行原測試。
- 主機圖形 QA 的字型來自公開 Noto Sans TC 測試素材；倉庫原有字型、應用程式圖示與簽章檔不因本機 QA 替換。
- 目前尚未合併 main、未建立 Tag／Release，APK 與正式服驗收仍待進行。

歷史 DESKTOP_SYNC_20261020.md、FEATURE_PARITY.md 及其他 Phase 文件是各階段紀錄，不代表本次已完成實機驗收。
