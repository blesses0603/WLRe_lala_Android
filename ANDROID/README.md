> **舊版警示：v0.0.2／v0.0.3 已重現 Keystore JNI 啟動崩潰；v0.0.4 已通過 Android 12～16 啟動相容性流程，請不要安裝舊產物。**

# WLRe_LaLa Android v0.0.7（實驗版）

沿用 Kivy 直式介面與 Python 協議核心。所有 Android 修改位於 `main`；版本與桌面版分開。

### 懸浮小球（Android v0.0.7）

在「服務與資源」點選 **開啟懸浮小球**，首次使用會開啟 Android「顯示在其他應用程式上層」的特殊權限頁。授權後返回 App，小球由現有前景服務管理，可拖曳、點擊展開帳號連線與自動戰鬥狀態，面板也提供返回 App 與隱藏小球。不需要另外建立背景服務；隱藏小球不會停止連線。為避免浮在其他 App 上時洩漏登入資料，帳號只顯示遮罩、沒有密碼或憑證。

小球採使用者主動開啟，不會在未授權時顯示。即使開啟了懸浮球，Android 仍可撤銷特殊權限、停止服務或關閉 App，且 Android 15 的 dataSync 前景服務仍有限時。首次發布後需要真機測試拖曳、展開／收合、鎖屏、返回桌面、權限撤銷與斷線狀態；模擬器通過不等同真機驗收。

## 本版功能

- 新增每帳號的完整觸控功能頁：角色概況、包包與特技、小地圖、戰場陣形、聊天、組隊、煉金、製作、經驗效率、事件紀錄及完整 AI／補給設定。詳見 [電腦／手機功能對照](FEATURE_PARITY.md)。

- 各帳號卡片新增自動戰鬥／自動徘徊啟動與停止，以及 AI 設定。設定依帳號＋伺服器保存，重新登入自動載入；不自動啟動操作。狀態依遊戲核心實際回報更新。

- 每個帳號使用獨立連線、停止旗標、選角佇列及狀態；沒有固定帳號數量上限。
- 連線移至獨立 Python 前景服務程序，畫面暫停或重建不停止服務；重新開啟可取回帳號卡片及目前狀態。
- 常駐通知可以返回畫面或停止全部連線；畫面也提供停止及重新啟動服務。
- 活動連線期間以有時限的 partial wake lock 保持 CPU，連線結束即釋放；TCP keepalive 協助偵測無回應的網路。
- 自願勾選保存時，用 Android Keystore AES-256-GCM 加密整份帳號資料；金鑰不可匯出，密文放在不備份的 App 私有目錄。可切換已保存帳號、刪除保存資料；刪除保存資料不會關閉其他既有連線。未勾選時不保存密碼。
- 畫面與服務透過私有 Unix socket 溝通，沒有 TCP 控制埠；密碼不寫入 IPC 檔案、參數、日誌或事件。
- 顯示帳號登入／選角／角色資訊與各自斷線狀態；服務失聯顯示未知，不能繼續顯示在線。
- 顯示活動連線、在線數、畫面／服務 PSS 記憶體、取樣時間、裝置電量及溫度。App 精確耗電無可靠公共 API，目前明確顯示未知，不把裝置掉電當作本 App 耗電。
- 整個表單及帳號清單可捲動，包含 Noto Sans TC 中文字型（OFL 授權附於 assets/fonts）。

## 背景限制與待驗收

Android 15 對 `dataSync` 前景服務有背景累計時限（通常為每 24 小時 6 小時）；時限到達會停止服務，回到前景後可手動重啟。通知、前景服務與 wake lock 不能保證繞過 Doze、廠商省電或無網路。系統停止服務後，不會偷偷自動重新登入。

v0.0.4 使用者實機畫面已確認登入及角色狀態同步；Android API 31～36 模擬器均通過啟動、Keystore 加解密、切換 App 與短暫鎖屏測試。v0.0.6 自動戰鬥／徘徊及 15／30／60 分鐘鎖屏仍須實機驗收。桌面測試不能代替這些結果。請參閱 [驗收表](ACCEPTANCE.md) 與 [驗證紀錄](VALIDATION.md)。

## APK 與開發測試

採用混合觸發模式：`main` 的程式碼更新會自動執行 `android-smoke.yml`（完整單元測試、語法檢查與 Android 12～16 模擬器測試），**不會因此自動編譯手機 APK**。推送符合 `v<主>.<次>.<修訂>` 格式的 Git Tag（例如 `v0.0.7`）才會自動觸發 `android-apk.yml`。兩套工作流程都保留 Actions 手動執行入口。

發布版本前，必須先讓 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION` 一致，並與 Git Tag 的版本相符；Tag 也必須指向 `main` 內的提交。手動 APK 建置僅允許從 `main` 執行，使用目前原始碼的版本號。

在 [Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) 的成功執行頁下載 `WLRe_LaLa-Android-v<版本號>-debug` Artifact，內含 `WLRe_LaLa-Android-v<版本號>-debug.apk` 與 `SHA256SUMS.txt`。打包成功不等於實機登入驗收通過。

```bash
pip install kivy==2.3.1 Pillow cryptography
KIVY_NO_ARGS=1 xvfb-run -a python -m unittest discover -s tests -p 'test_android*.py' -q
buildozer -v android debug
```

服務入口 `android_app/service.py`；IPC `runtime.py`；密文帳號庫 `vault.py`；Android 通知／超時處理位於 `android_app/java/`。Buildozer 固定 python-for-android revision，並固定 charset-normalizer 3.4.2，避免 Linux 主機 pip 拒收新 Android 專用 wheel 的跨編譯問題。

相容性流程 `android-smoke.yml` 以 API 31–36（Android 12／12L／13／14／15／16）測試啟動、Keystore 加解密及服務。開始編譯前也會核對 `buildozer.spec` 與 `android_app/version.py` 的版本設定一致；不要求 Git Tag，也不把版本號放進 smoke 的工作名稱或產物名稱。模擬器 Artifact 固定為 `Android-emulator-apk`，包含 `WLRe_LaLa-Android-emulator-debug.apk` 與 `SHA256SUMS.txt`，各 API 測試下載後會校驗 SHA256。模擬器 APK 不供手機安裝。最低 Android 版本為 12（API 31）。App 圖示由 `wlre/resources/assets/app.ico` 最大 256×256 圖層直接轉成 PNG 使用。
