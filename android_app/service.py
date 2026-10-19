"""python-for-android foreground-service entry point (separate process)."""
import json
import os
import time
from pathlib import Path
from android_app.runtime import Runtime
from android_app.sessions import SessionManager
from android_app.overlay_state import snapshot as overlay_snapshot


def main():
    from jnius import autoclass, cast
    service = autoclass('org.kivy.android.PythonService').mService
    from android_app.integrity import require_integrity, IntegrityRejected
    try:
        # The service runs in an independent Python process; never trust that
        # the Activity checked the signature already.
        require_integrity(service)
    except IntegrityRejected:
        print('WLRE_ANDROID_INTEGRITY_BLOCKED SERVICE', flush=True)
        service.stopSelf()
        return
    context = autoclass('android.content.Context')
    power = cast('android.os.PowerManager', service.getSystemService(context.POWER_SERVICE))
    wake = power.newWakeLock(1, 'WLRe_LaLa:connections')
    wake.setReferenceCounted(False)
    manager = SessionManager(settings_base=Path(str(service.getNoBackupFilesDir().getAbsolutePath())) / 'preferences')
    last_acquire = [0]
    # Keep overlay in the same foreground-service process as game sessions.
    # Failure to load an optional overlay must never terminate game connections.
    try:
        overlay = autoclass('org.lala.client.FloatingOverlay')
        overlay.restore(service)
    except Exception:
        overlay = None

    def overlay_control(enabled):
        if overlay is None: return False
        try: return bool(overlay.setEnabled(service, enabled))
        except Exception: return False

    def overlay_state():
        if overlay is None: return False
        try: return bool(overlay.isEnabled(service))
        except Exception: return False

    def refresh_overlay():
        if not overlay_state(): return
        try:
            state = overlay_snapshot(manager)
            overlay.updateStatus(service, json.dumps(state, ensure_ascii=False))
        except Exception:
            # Never let a visual overlay interfere with session keepalives.
            pass

    def metrics():
        active = sum(s.active for s in list(manager.sessions.values()))
        now = time.monotonic()
        if active and (not wake.isHeld() or now - last_acquire[0] > 240):
            wake.acquire(300000)  # Bounded lease; release as soon as connections end.
            last_acquire[0] = now
        elif not active and wake.isHeld():
            wake.release()
            last_acquire[0] = 0
        debug = autoclass('android.os.Debug')
        memory = autoclass('android.os.Debug$MemoryInfo')()
        debug.getMemoryInfo(memory)
        battery = service.registerReceiver(None, autoclass('android.content.IntentFilter')(
            'android.intent.action.BATTERY_CHANGED'))
        level, scale = (battery.getIntExtra('level', -1), battery.getIntExtra('scale', -1)) if battery else (-1, -1)
        battery_manager = cast('android.os.BatteryManager', service.getSystemService(context.BATTERY_SERVICE))
        current = battery_manager.getIntProperty(2)  # BATTERY_PROPERTY_CURRENT_NOW, device-wide microamps
        temperature = battery.getIntExtra('temperature', -1) if battery else -1
        refresh_overlay()
        return {'device_current_ua': current if current != -2147483648 else None,
                'device_temperature_c': temperature / 10 if temperature >= 0 else None,
                'sample_time': time.time(), 'service_pss_kib': memory.getTotalPss(),
                'active': active, 'online': sum(s.active and s.phase == 'world_ready'
                    for s in list(manager.sessions.values())),
                'battery_percent': round(level * 100 / scale) if level >= 0 and scale > 0 else None}

    directory = Path(str(service.getNoBackupFilesDir().getAbsolutePath())) / 'runtime'
    try:
        Runtime(manager, metrics, overlay_control=overlay_control,
                overlay_state=overlay_state).serve(directory / 'sessions.sock')
    finally:
        if overlay is not None:
            try: overlay.destroy(service)
            except Exception: pass
        if wake.isHeld(): wake.release()
        service.stopSelf()


if __name__ == '__main__': main()
