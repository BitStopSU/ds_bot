#!/usr/bin/env bash
set -e

APP_DIR="/opt/discord-bot"
SERVICE_NAME="discord-bot"
PYTHON_BIN="python3.11"

echo "=== Установка Discord-бота ==="

apt update -y
apt install -y python3.11 python3.11-venv python3-pip git curl sqlite3

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -f "main.py" ]; then
    echo "⚠️  Положи файлы бота в $APP_DIR (git clone или SFTP) и запусти снова."
    exit 1
fi

$PYTHON_BIN -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    read -p "Вставь DISCORD_TOKEN: " TOKEN
    read -p "Вставь GUILD_ID: " GUILD
    sed -i "s|DISCORD_TOKEN=.*|DISCORD_TOKEN=$TOKEN|" .env
    sed -i "s|GUILD_ID=.*|GUILD_ID=$GUILD|" .env
    echo "✅ .env создан"
fi

cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/main.py
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/bot.log
StandardError=append:$APP_DIR/bot.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo ""
echo "✅ Готово."
echo "Статус: systemctl status $SERVICE_NAME"
echo "Логи:   tail -f $APP_DIR/bot.log"
