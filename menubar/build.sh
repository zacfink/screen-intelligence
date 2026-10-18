#!/bin/sh
# Builds ~/Applications/Claude Status.app (menu bar only) from main.swift.
set -e
cd "$(dirname "$0")"
app="$HOME/Applications/Claude Status.app"
mkdir -p "$app/Contents/MacOS"
swiftc -O main.swift -o "$app/Contents/MacOS/ClaudeStatus"
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Claude Status</string>
<key>CFBundleIdentifier</key><string>ca.zacfinkelstein.claude-status</string>
<key>CFBundleExecutable</key><string>ClaudeStatus</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
echo "$app"
