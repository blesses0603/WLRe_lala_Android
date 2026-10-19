"""No-account emulator smoke test: UI, service, Home and screen-off survival.

Readiness and process assertions are required; transient ADB logcat errors
during startup and best-effort diagnostic collection must not conceal the
actual Android UI/service result. A true readiness timeout still fails.
"""
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ''):
    from android_diagnostic_redaction import summarize_logcat, summarize_services
else:
    from .android_diagnostic_redaction import summarize_logcat, summarize_services

PACKAGE = 'org.lala.client.wlrelala'
MARKERS = ('WLRE_ANDROID_UI_READY',
           'WLRE_ANDROID_SERVICE_CONNECTED',
           'WLRE_ANDROID_KEYSTORE_READY')


def adb(*args, check=True):
    return subprocess.run(['adb', *args], text=True, capture_output=True, check=check).stdout


def alive(name):
    return bool(adb('shell', 'pidof', name, check=False).strip())


def diagnostic_adb(*args):
    """Best-effort output: adb/logcat failures must not change smoke results."""
    failure = "unavailable"
    for attempt in range(2):
        try:
            result = subprocess.run(
                ['adb', *args], text=True, capture_output=True,
                check=False, timeout=15)
            if result.returncode == 0:
                return result.stdout
            failure = "adb returned exit code {}".format(result.returncode)
        except (OSError, subprocess.TimeoutExpired) as error:
            # Do not print raw stderr because it can contain device information.
            failure = type(error).__name__
        if attempt == 0:
            time.sleep(1)
    return "[diagnostic unavailable: {}]\n".format(failure)


def readiness_log():
    """Read startup markers without failing on transient emulator adb exit 255.

    A missing/failed read is never treated as a ready application.
    """
    try:
        result = subprocess.run(
            ['adb', 'logcat', '-d', '-v', 'threadtime'],
            text=True, capture_output=True, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        print("Startup logcat temporarily unavailable ({})".format(
            type(error).__name__), flush=True)
        return None
    if result.returncode != 0:
        print("Startup logcat temporarily unavailable (adb status {})".format(
            result.returncode), flush=True)
        return None
    return result.stdout


def wait_for_readiness(timeout=150):
    """Collect positive markers over retries; missing markers remain failures."""
    deadline = time.monotonic() + timeout
    found = set()
    while True:
        logs = readiness_log()
        if logs is not None:
            found.update(marker for marker in MARKERS if marker in logs)
            if len(found) == len(MARKERS):
                return
        if time.monotonic() >= deadline:
            missing = [marker for marker in MARKERS if marker not in found]
            raise RuntimeError(
                "UI/service readiness markers missing after {}s: {}".format(
                    timeout, ", ".join(missing)))
        time.sleep(2)


def collect_diagnostics(failed=False):
    """Always try to save useful logs without hiding the original test result."""
    try:
        logs = diagnostic_adb('logcat', '-d', '-v', 'threadtime')
        if logs.startswith("[diagnostic unavailable:"):
            # Bounded output can succeed when a full Android logcat dump fails.
            bounded = diagnostic_adb('logcat', '-d', '-t', '300',
                                     '-v', 'threadtime')
            if not bounded.startswith("[diagnostic unavailable:"):
                logs = "[full logcat unavailable; last 300 lines follow]\n" + bounded
        # Do not persist/print raw logcat; even a known marker line may carry
        # an accidentally logged credential or arbitrary service payload.
        safe = summarize_logcat(logs)
        Path('android-smoke-logcat.txt').write_text(safe, encoding='utf-8')
        if logs.startswith("[diagnostic unavailable:"):
            print("Smoke diagnostics: logcat unavailable; retaining startup-test result.", flush=True)
        if failed:
            print(safe, flush=True)
    except Exception as error:
        # A disk or tool error while collecting diagnostics is not an app failure.
        print("Smoke diagnostics: logcat capture failed ({})".format(
            type(error).__name__), flush=True)
    try:
        services = diagnostic_adb('shell', 'dumpsys', 'activity', 'services', PACKAGE)
        Path('android-smoke-services.txt').write_text(
            summarize_services(services), encoding='utf-8')
    except Exception as error:
        print("Smoke diagnostics: service dump failed ({})".format(
            type(error).__name__), flush=True)


def main():
    apk = next(Path('bin').glob('*.apk'))
    subprocess.run(['adb', 'install', '-r', '-g', str(apk)], check=True)
    adb('logcat', '-c')
    adb('shell', 'am', 'start', '-W', '-n',
        PACKAGE + '/org.kivy.android.PythonActivity')
    try:
        wait_for_readiness(timeout=150)
        assert alive(PACKAGE), 'Activity process exited'
        service = PACKAGE + ':service_Connections'
        assert alive(service), 'Foreground service process exited'
        adb('shell', 'input', 'keyevent', '3')  # Home, keep task intact.
        time.sleep(15)
        assert alive(service), 'Service exited after Home'
        adb('shell', 'input', 'keyevent', '223')  # Sleep.
        time.sleep(30)
        assert alive(service), 'Service exited while screen off'
        adb('shell', 'input', 'keyevent', '224')
        adb('shell', 'wm', 'dismiss-keyguard')
        adb('shell', 'am', 'start', '-W', '-n',
            PACKAGE + '/org.kivy.android.PythonActivity')
        time.sleep(5)
        assert alive(PACKAGE), 'Activity exited after resume'
        assert alive(service), 'Service exited after resume'
        print('Android UI + foreground service + Home + 30-second screen-off '
              'smoke passed (no accounts/network login)', flush=True)
    finally:
        collect_diagnostics(failed=sys.exc_info()[0] is not None)


if __name__ == '__main__':
    main()
