#!/usr/bin/env bash
SERVICE="discord-bot"
APP_DIR="/opt/discord-bot"
cd "$APP_DIR"

case "$1" in
    start)     systemctl start "$SERVICE" ;;
    stop)      systemctl stop "$SERVICE" ;;
    restart)   systemctl restart "$SERVICE" ;;
    status)    systemctl status "$SERVICE" ;;
    logs)      tail -f "$APP_DIR/bot.log" ;;
    update)
        git pull
        source venv/bin/activate
        pip install -r requirements.txt
        systemctl restart "$SERVICE"
        ;;
    backup)
        mkdir -p backups
        sqlite3 bot.db ".backup backups/bot_$(date +%Y%m%d_%H%M%S).db"
        echo "✅ Бэкап создан"
        ;;
    *)
        echo "Использование: ./manage.sh {start|stop|restart|status|logs|update|backup}"
        ;;
esac
