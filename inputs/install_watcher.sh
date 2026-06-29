#!/bin/bash
# One-time setup: installs the screenshot watcher as a macOS Launch Agent.
# Run once: bash install_watcher.sh
# After this, the watcher starts automatically on login — no Terminal needed.

PLIST="$HOME/Library/LaunchAgents/com.booky.screenshot-watcher.plist"
PYTHON="/Users/$(whoami)/anaconda3/bin/python"
SCRIPT="/path/to/booky-growth-report/inputs/screenshot_watcher.py"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.booky.screenshot-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/screenshot_watcher.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/screenshot_watcher.log</string>
</dict>
</plist>
EOF

# Load it now (no reboot needed)
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

echo "✓ Launch Agent installed and started."
echo "✓ Watcher will auto-start on every login from now on."
echo "  Log: /tmp/screenshot_watcher.log"
echo "  To uninstall: launchctl unload $PLIST && rm $PLIST"
