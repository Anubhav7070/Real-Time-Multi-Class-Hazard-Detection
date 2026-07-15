#!/usr/bin/env python3
"""
test_phone_notifications.py
============================
Quick test to verify phone notifications are working with ntfy.sh

Usage:
    python test_phone_notifications.py
"""

import sys
import time
from config import SystemConfig, RiskLevel
from alert_manager import AlertManager


def test_dependencies():
    """Check if required libraries are installed."""
    print("\n" + "="*60)
    print("  DEPENDENCY CHECK")
    print("="*60)
    
    deps = {
        "requests": "Required for phone notifications to ntfy.sh",
        "plyer": "Optional - desktop notifications",
        "pygame": "Optional - sound alerts",
    }
    
    all_ok = True
    for pkg, desc in deps.items():
        try:
            __import__(pkg)
            print(f"  ✓ {pkg:20} {desc}")
        except ImportError:
            status = "MISSING" if pkg == "requests" else "optional"
            print(f"  ✗ {pkg:20} {desc} [{status}]")
            if pkg == "requests":
                all_ok = False
    
    return all_ok


def test_config():
    """Check configuration settings."""
    print("\n" + "="*60)
    print("  CONFIGURATION CHECK")
    print("="*60)
    
    config = SystemConfig()
    
    checks = {
        "phone_notify_enabled": config.phone_notify_enabled,
        "ntfy_topic set": config.ntfy_topic is not None and len(config.ntfy_topic) > 0,
        "ntfy_server": config.ntfy_server,
    }
    
    print(f"  Phone notifications enabled : {config.phone_notify_enabled}")
    print(f"  Topic                       : {config.ntfy_topic}")
    print(f"  Server                      : {config.ntfy_server}")
    
    if config.phone_notify_enabled and config.ntfy_topic:
        print(f"\n  Subscribe to notifications at:")
        print(f"  🔗  https://ntfy.sh/{config.ntfy_topic}")
        return True
    else:
        print("\n  ⚠️  Phone notifications DISABLED or topic not set!")
        return False


def test_network():
    """Test connectivity to ntfy.sh"""
    print("\n" + "="*60)
    print("  NETWORK CHECK")
    print("="*60)
    
    try:
        import requests
        config = SystemConfig()
        
        print(f"  Testing connection to: {config.ntfy_server}")
        
        response = requests.head(config.ntfy_server, timeout=5)
        if response.status_code < 400:
            print(f"  ✓ Server reachable (HTTP {response.status_code})")
            return True
        else:
            print(f"  ✗ Server returned HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"  ✗ Cannot connect to ntfy.sh")
        print(f"     Check your internet connection or firewall settings")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_phone_alert():
    """Send a test phone alert."""
    print("\n" + "="*60)
    print("  PHONE ALERT TEST")
    print("="*60)
    
    config = SystemConfig()
    alert = AlertManager(config)
    
    print("\n  Sending test notification for POISONOUS PLANT detection...")
    print(f"  Plant: datura (deadly)")
    print(f"  Risk Level: HIGH")
    
    # Send alert
    alert.handle(
        risk_level=RiskLevel.HIGH,
        animal_name="datura",
        category="plant"
    )
    
    print("\n  ⏳ Waiting 3 seconds for alert to process...")
    time.sleep(3)
    
    return True


def main():
    print("\n" + "█"*60)
    print("█" + " "*58 + "█")
    print("█" + "  WILDLIFE DETECTION - PHONE NOTIFICATION TEST".center(58) + "█")
    print("█" + " "*58 + "█")
    print("█"*60)
    
    # Run tests
    deps_ok = test_dependencies()
    config_ok = test_config()
    net_ok = test_network()
    
    if not deps_ok:
        print("\n" + "!"*60)
        print("  ERROR: Missing 'requests' library!")
        print("  Fix: pip install requests")
        print("!"*60 + "\n")
        return False
    
    if not config_ok:
        print("\n" + "!"*60)
        print("  ERROR: Phone notifications not properly configured!")
        print("  Fix: Set phone_notify_enabled=True and ntfy_topic in config.py")
        print("!"*60 + "\n")
        return False
    
    if not net_ok:
        print("\n" + "!"*60)
        print("  ERROR: Cannot reach ntfy.sh server!")
        print("  Fix: Check internet connection or firewall")
        print("!"*60 + "\n")
        return False
    
    # All checks passed - send test alert
    test_phone_alert()
    
    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)
    print("\n  ✓ All checks passed!")
    print("\n  Next steps:")
    print(f"    1. Go to: https://ntfy.sh/{SystemConfig().ntfy_topic}")
    print("    2. You should see the test notification appear")
    print("    3. Run your detection system and watch for alerts")
    print("\n" + "="*60 + "\n")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
