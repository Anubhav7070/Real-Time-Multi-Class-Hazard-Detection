"""
alert_manager.py
================
Alert system — sound, desktop notifications, and phone push via
the built-in Wildlife Alert Notification Server (notification_server.py).

No third-party services needed.  Run notification_server.py on your PC,
then open the PWA on your phone: http://<PC-IP>:8765/app

SETTINGS:
  - Desktop popup  : ON for ALL risk levels (HIGH / MEDIUM / LOW)
  - Sound alarm    : ON for ALL risk levels
  - Phone (WebSocket PWA): ON for ALL risk levels
  - Cooldown       : Desktop/Sound = config.alert_cooldown (default 3s)
                     Phone         = PHONE_COOLDOWN         (default 10s)
"""

import time
import threading
import platform
import sys
from config import RiskLevel, SystemConfig


class AlertManager:

    PHONE_COOLDOWN = 10.0   # seconds between phone pushes

    def __init__(self, config: SystemConfig):
        self.config           = config
        self._last_high       = 0.0
        self._last_med        = 0.0
        self._last_low        = 0.0
        self._last_phone_high = 0.0
        self._last_phone_med  = 0.0
        self._last_phone_low  = 0.0
        self._sound_lock      = threading.Lock()

        self._plyer_ok    = self._check("plyer")
        self._pygame_ok   = self._check("pygame")
        self._requests_ok = self._check("requests")

        print("[INFO]  ── Alert Channels ──────────────────────────")
        print("[INFO]  Desktop notify :", "plyer OK ✓" if self._plyer_ok
              else "plyer missing — run: pip install plyer")
        print("[INFO]  Sound alerts   :", "pygame OK ✓" if self._pygame_ok
              else "pygame missing — run: pip install pygame")
        if config.phone_notify_enabled:
            print(f"[INFO]  Phone alerts   : Custom server → http://localhost:{config.notify_server_port}/app ✓")
            print(f"[INFO]  Open on phone  : http://<PC-IP>:{config.notify_server_port}/app")
        else:
            print("[INFO]  Phone alerts   : DISABLED (set phone_notify_enabled=True in config)")
        print("[INFO]  Notify on      : ALL detections (HIGH + MEDIUM + LOW)")
        print("[INFO]  ─────────────────────────────────────────────")

    # ── Availability checks ──────────────────────────────────────

    def _check(self, pkg: str) -> bool:
        try:
            __import__(pkg)
            return True
        except ImportError:
            return False

    # ── Public API ───────────────────────────────────────────────

    def handle(self, risk_level: str, animal_name: str = "Unknown",
               category: str = "animal"):
        """
        Fire alerts for ANY risk level — HIGH, MEDIUM, or LOW.
        NONE = nothing detected, skipped silently.
        """
        if risk_level == RiskLevel.NONE:
            return

        now       = time.time()
        cat_upper = (category or "THREAT").upper()
        cat_lower = (category or "threat").lower()
        name      = (animal_name or "Unknown").replace("_", " ").title()
        name_with_category = f"{name} {cat_lower}"

        # ── HIGH ────────────────────────────────────────────────
        if risk_level == RiskLevel.HIGH:
            if now - self._last_high >= self.config.alert_cooldown:
                self._last_high = now
                print(f"[ALERT]  HIGH RISK — {name_with_category} detected!")
                if self.config.notify_enabled:
                    self._send_desktop(
                        title   = f"HIGH RISK — {name_with_category}!",
                        message = f"{name_with_category.title()} is dangerously close to a person!",
                        urgency = "critical",
                    )
                if self.config.sound_enabled:
                    self._play_alarm(level="high")

            if (self.config.phone_notify_enabled
                    and now - self._last_phone_high >= self.PHONE_COOLDOWN):
                self._last_phone_high = now
                self._send_phone(
                    title    = f"HIGH RISK: {name_with_category}",
                    message  = f"{name_with_category.title()} dangerously close to a person!",
                    priority = "urgent",
                    tags     = "warning,rotating_light,red_circle",
                    risk_level = RiskLevel.HIGH,
                    animal   = animal_name,
                    category = category,
                )

        # ── MEDIUM ───────────────────────────────────────────────
        elif risk_level == RiskLevel.MEDIUM:
            if now - self._last_med >= self.config.alert_cooldown:
                self._last_med = now
                print(f"[ALERT]  MEDIUM RISK — {name_with_category} nearby")
                if self.config.notify_enabled:
                    self._send_desktop(
                        title   = f"{name_with_category.title()} Nearby",
                        message = f"{name_with_category.title()} detected nearby. Stay alert!",
                        urgency = "normal",
                    )
                if self.config.sound_enabled:
                    self._play_alarm(level="medium")

            if (self.config.phone_notify_enabled
                    and now - self._last_phone_med >= self.PHONE_COOLDOWN):
                self._last_phone_med = now
                self._send_phone(
                    title    = f"{name_with_category.title()} Detected",
                    message  = f"{name_with_category.title()} nearby — monitor the situation.",
                    priority = "high",
                    tags     = "eyes,large_orange_circle",
                    risk_level = RiskLevel.MEDIUM,
                    animal   = animal_name,
                    category = category,
                )

        # ── LOW ──────────────────────────────────────────────────
        elif risk_level == RiskLevel.LOW:
            if now - self._last_low >= self.config.alert_cooldown:
                self._last_low = now
                print(f"[ALERT]  LOW RISK — {name_with_category} spotted")
                if self.config.notify_enabled:
                    self._send_desktop(
                        title   = f"{name_with_category.title()} Spotted",
                        message = f"{name_with_category.title()} detected at safe distance.",
                        urgency = "low",
                    )
                if self.config.sound_enabled:
                    self._play_alarm(level="low")

            if (self.config.phone_notify_enabled
                    and now - self._last_phone_low >= self.PHONE_COOLDOWN):
                self._last_phone_low = now
                self._send_phone(
                    title    = f"{name_with_category.title()} Spotted",
                    message  = f"{name_with_category.title()} at safe distance — FYI.",
                    priority = "default",
                    tags     = "eyes,large_yellow_circle",
                    risk_level = RiskLevel.LOW,
                    animal   = animal_name,
                    category = category,
                )

    # ── Desktop Notification ─────────────────────────────────────

    def _send_desktop(self, title: str, message: str, urgency: str = "normal"):
        threading.Thread(
            target=self._desktop_worker,
            args=(title, message, urgency),
            daemon=True,
        ).start()

    def _desktop_worker(self, title: str, message: str, urgency: str):
        # 1. Try plyer (most reliable cross-platform)
        if self._plyer_ok:
            try:
                from plyer import notification
                notification.notify(
                    title    = title,
                    message  = message,
                    app_name = "Wildlife Detector",
                    timeout  = 6,
                )
                return
            except Exception:
                pass

        # 2. Windows fallbacks
        if platform.system() == "Windows":
            # win10toast
            try:
                from win10toast import ToastNotifier
                ToastNotifier().show_toast(title, message, duration=5, threaded=True)
                return
            except Exception:
                pass
            # PowerShell toast
            try:
                import subprocess
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms;"
                    "$n = New-Object System.Windows.Forms.NotifyIcon;"
                    "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                    "$n.Visible = $true;"
                    f"$n.ShowBalloonTip(5000, '{title}', '{message}', "
                    "[System.Windows.Forms.ToolTipIcon]::Warning);"
                    "Start-Sleep -Seconds 6; $n.Dispose()"
                )
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                    creationflags=0x08000000   # CREATE_NO_WINDOW
                )
                return
            except Exception as e:
                print(f"[WARN]  Desktop notify fallback error: {e}")

        elif platform.system() == "Darwin":
            import subprocess
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                check=False,
            )
        elif platform.system() == "Linux":
            import subprocess
            subprocess.run(["notify-send", title, message], check=False)

    # ── Sound ────────────────────────────────────────────────────

    def _play_alarm(self, level: str = "high"):
        threading.Thread(
            target=self._sound_worker,
            args=(level,),
            daemon=True,
        ).start()

    def _sound_worker(self, level: str):
        if self._pygame_ok:
            try:
                import pygame
                import numpy as np

                with self._sound_lock:
                    if pygame.mixer.get_init():
                        pygame.mixer.quit()
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                    SR = 44100

                    def make_tone(freq: float, dur: float):
                        t      = np.linspace(0, dur, int(SR * dur), False)
                        wave   = np.sin(2 * np.pi * freq * t)
                        fade   = int(SR * 0.01)
                        wave[:fade]  *= np.linspace(0, 1, fade)
                        wave[-fade:] *= np.linspace(1, 0, fade)
                        mono   = (wave * 32767).astype(np.int16)
                        stereo = np.column_stack((mono, mono))
                        return pygame.sndarray.make_sound(stereo)

                    if level == "high":
                        # 3× urgent alternating beeps
                        for _ in range(3):
                            make_tone(1000, 0.25).play()
                            while pygame.mixer.get_busy(): time.sleep(0.01)
                            make_tone(500,  0.25).play()
                            while pygame.mixer.get_busy(): time.sleep(0.01)

                    elif level == "medium":
                        # 2× medium beeps
                        for _ in range(2):
                            make_tone(700, 0.3).play()
                            while pygame.mixer.get_busy(): time.sleep(0.01)
                            time.sleep(0.08)

                    else:  # low
                        # 1× soft beep
                        make_tone(500, 0.2).play()
                        while pygame.mixer.get_busy(): time.sleep(0.01)
                return
            except Exception as e:
                print(f"[WARN]  Sound error: {e}")

        # Terminal bell fallback
        count = {"high": 3, "medium": 2, "low": 1}.get(level, 1)
        for _ in range(count):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.3)

    # ── Phone push (custom WebSocket notification server) ────────

    def _send_phone(self, title: str, message: str,
                    priority: str = "default", tags: str = "eyes",
                    risk_level: str = "LOW", animal: str = "unknown",
                    category: str = "animal"):
        if not (self._requests_ok and self.config.phone_notify_enabled):
            return
        threading.Thread(
            target=self._phone_worker,
            args=(title, message, priority, tags, risk_level, animal, category),
            daemon=True,
        ).start()

    def _phone_worker(self, title: str, message: str, priority: str, tags: str,
                      risk_level: str, animal: str, category: str):
        try:
            import requests
            url = (f"http://localhost:{self.config.notify_server_port}/alert")
            payload = {
                "risk_level": risk_level,
                "title":      title,
                "message":    message,
                "priority":   priority,
                "tags":       tags,
                "animal":     animal,
                "category":   category,
            }
            resp = requests.post(url, json=payload, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                clients = data.get("clients_notified", 0)
                print(f"[INFO]  Phone alert sent ✓ — {title}  ({clients} client(s) notified)")
            else:
                print(f"[WARN]  Notification server HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"[WARN]  Notification server not running — start notification_server.py")
        except requests.exceptions.Timeout:
            print(f"[WARN]  Notification server timeout")
        except Exception as e:
            print(f"[ERROR] Phone alert error: {type(e).__name__}: {e}")