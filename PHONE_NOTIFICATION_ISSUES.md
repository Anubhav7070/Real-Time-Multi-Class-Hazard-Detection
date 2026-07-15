# Phone Notification Issues - Analysis & Fixes

## Problem Summary
When poisonous plants are detected, phone notifications are not being sent. This happens due to **configuration and dependency issues**.

---

## Root Causes Identified

### 1. ❌ **Missing HTTP Library (`requests`)**
The alert system requires the `requests` library to send notifications to ntfy.sh, but:
- Check if `requests` is installed: `pip list | grep requests`
- The requirements.txt includes it, but it might not be installed in your venv

### 2. ❌ **Network/Connectivity Issues**
- ntfy.sh requires an active internet connection
- The request might be failing silently (caught exception not visible)
- Firewall might be blocking the connection

### 3. ⚠️ **Error Logging Too Quiet**
The `_phone_worker()` method catches exceptions but only prints warnings, making it hard to debug

---

## Solutions

### Step 1: Install Missing Dependencies
```bash
pip install requests
pip install plyer pygame
```

### Step 2: Verify Configuration
Check your `config.py` has these settings:
```python
phone_notify_enabled  : bool          = True     # Must be True
ntfy_topic            : Optional[str] = "wildlife-alerts-anubhav"  # Must have a topic
ntfy_server           : str           = "https://ntfy.sh"  # Check connectivity
```

### Step 3: Test Phone Notifications Manually
Create a test script `test_phone_notif.py`:
```python
from config import SystemConfig
from alert_manager import AlertManager

config = SystemConfig()
alert = AlertManager(config)

# Test sending a phone notification
alert.handle(
    risk_level="HIGH",
    animal_name="datura",
    category="plant"
)

print("✓ Notification request sent to ntfy.sh")
print(f"  Subscribe at: https://ntfy.sh/{config.ntfy_topic}")
```

Run it: `python test_phone_notif.py`

### Step 4: Subscribe to Notifications
Go to: `https://ntfy.sh/wildlife-alerts-anubhav`
- You should see notifications appear here when the detector runs
- Or use a mobile app (iOS: Noto, Android: ntfy)

### Step 5: Add Better Error Logging
Modify `alert_manager.py` to show network errors:

```python
def _phone_worker(self, title: str, message: str, priority: str, tags: str):
    try:
        import requests
        url  = f"{self.config.ntfy_server}/{self.config.ntfy_topic}"
        
        print(f"[DEBUG] Sending to: {url}")  # Add this line
        
        resp = requests.post(
            url,
            data    = message.encode("utf-8"),
            headers = {
                "Title":        title,
                "Priority":     priority,
                "Tags":         tags,
                "Content-Type": "text/plain; charset=utf-8",
            },
            timeout = 5,
        )
        if resp.status_code == 200:
            print(f"[INFO]  Phone alert sent ✓ — {title}")
        else:
            print(f"[WARN]  Phone alert HTTP {resp.status_code} — {resp.text}")  # Show response
    except Exception as e:
        print(f"[WARN]  Phone alert error: {type(e).__name__}: {e}")  # Better error info
```

---

## Quick Checklist

- [ ] Run `pip install requests` in your venv
- [ ] Verify `phone_notify_enabled = True` in config.py
- [ ] Verify `ntfy_topic = "wildlife-alerts-anubhav"` is set
- [ ] Test with: `python test_phone_notif.py`
- [ ] Go to `https://ntfy.sh/wildlife-alerts-anubhav` to subscribe
- [ ] Run detection again and check if notifications appear

---

## How It Works (Flow)

```
Poisonous Plant Detected
    ↓
detector._process_frame()
    ↓
risk_engine.assess_frame() → RiskLevel.HIGH/MEDIUM/LOW
    ↓
alert.handle(risk_level, plant_name, category="plant")
    ↓
alert._send_phone() → requests.post(ntfy.sh)
    ↓
Notification sent to your phone/web
```

**For alerts to reach your phone:**
1. Plant must be detected (via YOLOv8)
2. Risk level must NOT be NONE
3. `phone_notify_enabled = True`
4. `ntfy_topic` must be set
5. `requests` library must be installed
6. Internet connection required

---

## Alternative: Use ngrok for Local Testing
If ntfy.sh is blocked, you can test locally:
```bash
ngrok http 8000
# Create a simple Flask endpoint to log notifications
```

