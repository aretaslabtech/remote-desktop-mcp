#!/bin/bash
set -e

# 1. Permanent Snap Ban
cat <<EOF | sudo tee /etc/apt/preferences.d/nosnap
Package: snapd
Pin: release a=*
Pin-Priority: -10
EOF

sudo apt-get purge -y snapd || true

# 2. Add Mozilla Repositories
sudo install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | sudo tee /etc/apt/sources.list.d/mozilla.list > /dev/null

cat <<EOF | sudo tee /etc/apt/preferences.d/mozilla
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000
EOF

# 3. Core Installation
sudo apt-get update
sudo apt-get install --no-install-recommends -y xfce4 xfce4-goodies firefox xrdp dbus-x11 nodejs git curl npm

# 4. Configuration
echo "ubuntu:ubuntu" | sudo chpasswd
echo "xfce4-session" > /home/ubuntu/.xsession
chown ubuntu:ubuntu /home/ubuntu/.xsession

sudo apt-get remove -y light-locker xscreensaver
sudo apt-get autoremove -y

# 5. Claude Code Setup
sudo npm install -g @anthropic-ai/claude-code

# 6. Service Start
sudo systemctl enable xrdp
sudo systemctl restart xrdp

echo "Setup complete. Connect via RDP: ubuntu/ubuntu"
