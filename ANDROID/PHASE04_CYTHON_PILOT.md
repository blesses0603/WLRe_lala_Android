# 第 04 項｜ARM64 Cython 保護試點：準備與驗收計畫

> 2026-10-19，基準 main `1aa458689322368f6124e7189d630fa4a00db765`、Android v0.0.7、min API 31、arm64-v8a。
> **狀態：已實作隔離原生試驗建置流程，但尚未取得 Android ARM64 APK／真機驗收。**

## 與前階段的界線

- 第 01 項：原始碼與 APK 的安全現況盤點。
- 第 02 項：固定 Debug APK 簽章、公開 SHA256 pin 與重簽驗收；沿用原來的 Repository Secret／Variable，不取出也不重建私鑰。
- 第 03 項：敏感核心清單、APK 封裝檢查與 bytecode 風險揭露。
- **第 04 項：先選一個低耦合但跨模組使用的核心進行 Cython 原生化試點，建立行為等價、Android ABI、匯入與封裝驗證；通過後才擴大。**
- 第 05 項：逐步擴及其他 P0/P1 核心，需逐一回歸與實機驗收。

## 試點選擇

**目標模組：`wlre/network/wire.py`**

主要使用者為 `wlre/network/client.py`、`wlre/network/protocol.py` 與其他引用封包原語的模組。公共 API 必須保留 `ProtocolError`、`Reader`、`Writer`、`Packet`、`encode`、`FrameDecoder`，尤其是 `Packet` dataclass 行為、TCP 分段接收、UTF-16LE 字串讀取、XOR 封包以及異常型別與文字。

該模組是**協定處理核心**，而不是保存使用者私鑰的地方。Cython 的目的為提高 bytecode 靜態還原成本，不代表密碼學保護、反動態 Hook 或不可逆向。

## 已建立的試點工具（不耗 Android Actions 分鐘）

- `tests/test_android_cython_wire.py`：使用合成封包固定協定 golden vectors 與錯誤行為；純 Python 測試可列入日常快速回歸。
- `python tools/android_cython_wire.py`：檢查當前 `wire.py` 基準 API。
- `python tools/android_native_wire.py host-smoke`：以真實 `_wlre_wire_native` 命名及 `wlre.network.wire` shim，在臨時目錄對比 Python 與 Cython 封包與例外快照（仍非 Android）。
- `python tools/android_cython_wire.py --host-smoke`：在**系統臨時資料夾**複製純 Python 封包模組、以主機 Cython + C 編譯器產生暫存擴充套件，在兩個相互隔離的程序對比輸出；結束後清除臨時資料。必須另外安裝 Cython、setuptools 和主機編譯器。**預設不自動執行 host-smoke**。

本地預備檢查（主機 Cython 3.2.4）：純 Python golden tests 4 項通過；新增 native staging／APK 模擬安全測試 5 項通過；實際原始 wire 模組已編譯成 Linux x86_64 `_wlre_wire_native`，透過正式樣式 shim 執行封包 golden vectors，與純 Python 輸出一致。這**不是**專案完整回歸，也不是使用 CI 的 `cython<3` 或 Android NDK 編譯結果。

## 實際操作（使用有 Android SDK／NDK 的 Linux）

**這是實驗建置，不會產生一般手機更新用的正式驗收 APK。** 先於本分支根目錄執行：

```bash
python -m unittest tests.test_android_cython_wire tests.test_android_native_wire -v
python tools/android_cython_wire.py --host-smoke
python tools/android_native_wire.py host-smoke   # 驗證實際 recipe 的 _wlre_wire_native + shim 等價

# --output 必須在 Git repo 外部；工具不會覆蓋已有資料夾。
python tools/android_native_wire.py stage --output /tmp/wlre-native-wire-stage
cd /tmp/wlre-native-wire-stage
buildozer -v android debug
```

編譯完成後，回到原分支的工具程式，對實際 APK 執行：

```bash
python tools/android_native_wire.py verify-apk /tmp/wlre-native-wire-stage/bin/<實際APK檔名>.apk
python tools/android_hardening.py report /tmp/wlre-native-wire-stage/bin/<實際APK檔名>.apk
```

最後仍需經完整既有固定簽章、SHA256、啟動畫面與真機驗收，才可提供使用者安裝。實驗 APK 若用隨機 Debug 憑證簽署，**不能當作固定簽章升級包**。建議不要使用真實遊戲帳密驗證不可信的未簽核建置。

## ARM64 原生編譯方案與實際準備結果

1. 維持上游已固定的 `p4a.commit`、`python3` 與正式版 `buildozer.spec`。已新增 `p4a-recipes/lalawire/`，使用 `IncludedFilesBehaviour` + `CythonRecipe`，以 p4a/NDK 編譯名稱為 `_wlre_wire_native` 的 extension。**還未以專案所固定的 p4a.commit 實際編譯測試。**
2. 已新增 `tools/android_native_wire.py stage`：將整個 App 複製至獨立資料夾，將完整 `wire.py` 複製為 local recipe 的 `_wlre_wire_native.pyx`，原 `wlre/network/wire.py` 在暫存專案只保留原生導入 shim；Buildozer 暫存設定增加 `lalawire` requirement 與 `p4a.local_recipes`，並排除 `p4a-recipes` 不進入 App。正式原始碼與既有標準版 Buildozer 設定**完全不改**。
3. 暫存版透過原本路徑 `wlre.network.wire` 匯入 `_wlre_wire_native` 中的 `ProtocolError`、`Reader`、`Writer`、`Packet`、`encode`、`FrameDecoder`。**Android App 與前景服務是否都能找到 site-packages 中的 native extension，仍需 Android 編譯／啟動檢查。**
4. 已新增 `tools/android_native_wire.py verify-apk`：拒絕沒有 ARM64 ELF 的 `_wlre_wire_native*.so`、發現原始實作的 `.py`／`.pyx`／`.pyc` 或未檢出 native extension 的 APK。保留 `wlre/network/wire.py` 的小型兼容 shim 於 App（仍會有少量 shim `.pyc`），**只有原本核心邏輯移出 bytecode，才符合目標**。
5. 已實作檢查 APK ZIP 與 `assets/private.tar` 的 ELF header（machine=AArch64）和敏感模組原始碼；**目前尚未有實際 APK，因此不能確認產物放置位置是否符合 p4a 目前版本，也不能聲稱可載入**。實際驗證必須比對 native import、封包與服務運行，必要時修正 recipe 與檢查器。
6. 保留 `tools/android_signing.py`、`ANDROID_DEBUG_KEYSTORE_BASE64`、`ANDROID_EXPECTED_SIGNER_SHA256`、既有 Release 流程，**不變更簽章憑證**；手動／Tag APK 打包成功後才驗證完整簽署報告。

p4a 參考：[官方 Recipes／CythonRecipe 文件](https://python-for-android.readthedocs.io/en/latest/recipes.html)。目前已新增本地 recipe 與實驗性分離建置接線；**但尚未在 Android SDK／NDK 編譯成功，不能列為已完成保護**。

## 驗收門檻

| 類型 | 必須完成的證據 | 目前 |
| --- | --- | --- |
| 純 Python 協定 golden vectors | 4 項新增測試 + 原有完整回歸 | 新增測試本地通過；完整回歸未執行 |
| Cython 主機編譯行為等價 | Python／Linux host extension 相同合成輸出 | 本地試點通過（非 Android） |
| Android ARM64 NDK 擴充套件 | 正確 ABI、模組名稱、輸入輸出、錯誤行為 | 已備 recipe／分離建置；尚未執行真正編譯 |
| 應用＋前景服務 import | 同一 Android-native 擴充套件可載入 | 未執行 |
| APK 排除原始碼與同名 bytecode | 保留小型 shim，但核心 `.pyc` 不得殘留 | 已寫測試工具；未取得真正 APK |
| 發佈安全 | 固定簽章 + 公開 pin + SHA256 + 安全掃描 | 此階段未產生新 APK |
| Android 12+ ARM64 真機 | 啟動、登入、分段收包、背景連線、功能回歸 | 未執行 |

## Actions 額度不足時的操作原則

- 第 04 項分支**不修改正常版 `buildozer.spec` 與 `.github/workflows/android-apk.yml`**，不會意外啟用未驗收 native 模組。Recipe 僅在 stage 產生的獨立暫存專案中啟用；也不手動觸發 GitHub 完整 APK。
- 可先在本地或恢復額度後跑 `python -m unittest tests.test_android_cython_wire -v` 與其他快速回歸；正式 ARM64 的安全與相容性必須等待有建置資源時再做。
- **未完成上述 APK/真機門檻前，不合併任何會取代 `wire.py` 的 Cython 打包變更到 main。**

## 回退方式

在編譯方案不相容時，取消原生 recipe／來源排除修改，維持目前純 Python `wlre.network.wire`，避免破壞登入、IPC 與遊戲封包處理。若已建立 APK，回退需要完整重新編譯並維持既有固定簽章身份。
