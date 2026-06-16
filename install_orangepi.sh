#!/bin/bash

set -e

# ==========================================================
# Автоматическая настройка Orange Pi / Linux mini PC
# sudo без пароля + node_exporter + x11vnc + websockify + noVNC
# + автоперенос kkt-tools в домашний каталог
# ==========================================================

USERNAME="orangepi"
VNC_PASSWORD="orangepi"

NODE_EXPORTER_VERSION="1.6.1"
NODE_EXPORTER_PORT="9100"
VNC_PORT="5900"
NOVNC_PORT="8080"

export DEBIAN_FRONTEND=noninteractive

echo "=========================================================="
echo " Старт настройки Orange Pi"
echo "=========================================================="

# ----------------------------------------------------------
# Проверка запуска от root / sudo
# ----------------------------------------------------------

if [ "$EUID" -ne 0 ]; then
  echo "Ошибка: скрипт нужно запускать через sudo:"
  echo "sudo bash install_orangepi.sh"
  exit 1
fi

# ----------------------------------------------------------
# Проверка пользователя
# ----------------------------------------------------------

if ! id "$USERNAME" >/dev/null 2>&1; then
  echo "Ошибка: пользователь $USERNAME не найден."
  echo "Если пользователь другой, измени переменную USERNAME в начале скрипта."
  exit 1
fi

USER_HOME="/home/$USERNAME"

echo "Пользователь для настройки: $USERNAME"
echo "Домашняя папка: $USER_HOME"
echo "Пароль VNC/noVNC будет установлен: $VNC_PASSWORD"

# ----------------------------------------------------------
# Ожидание освобождения apt/dpkg
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " Проверка блокировок apt/dpkg"
echo "=========================================================="

while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
      fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
      fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
  echo "apt/dpkg занят другим процессом. Ждём 10 секунд..."
  sleep 10
done

dpkg --configure -a || true

# ----------------------------------------------------------
# 1. Настройка sudo без пароля
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 1. Настройка sudo без пароля"
echo "=========================================================="

echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > "/etc/sudoers.d/nopasswd-$USERNAME"
chmod 0440 "/etc/sudoers.d/nopasswd-$USERNAME"

echo "Проверяем sudoers..."
visudo -cf "/etc/sudoers.d/nopasswd-$USERNAME"

echo "sudo без пароля настроен."

# ----------------------------------------------------------
# 2. Установка необходимых пакетов
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 2. Установка необходимых пакетов"
echo "=========================================================="

apt-get update
apt-get install -y wget curl tar git python3 x11vnc websockify novnc net-tools

echo "Пакеты установлены."

# ----------------------------------------------------------
# 3. Определение архитектуры и установка node_exporter
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 3. Установка node_exporter"
echo "=========================================================="

ARCH="$(uname -m)"

case "$ARCH" in
  aarch64)
    NODE_ARCH="arm64"
    ;;
  armv7l)
    NODE_ARCH="armv7"
    ;;
  armv6l)
    NODE_ARCH="armv6"
    ;;
  x86_64)
    NODE_ARCH="amd64"
    ;;
  *)
    echo "Ошибка: неподдерживаемая архитектура: $ARCH"
    echo "Проверь архитектуру командой: uname -m"
    exit 1
    ;;
esac

echo "Архитектура процессора: $ARCH"
echo "Версия node_exporter: linux-$NODE_ARCH"

cd /tmp

NODE_EXPORTER_ARCHIVE="node_exporter-${NODE_EXPORTER_VERSION}.linux-${NODE_ARCH}.tar.gz"
NODE_EXPORTER_DIR="node_exporter-${NODE_EXPORTER_VERSION}.linux-${NODE_ARCH}"
NODE_EXPORTER_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${NODE_EXPORTER_ARCHIVE}"

echo "Скачиваем node_exporter:"
echo "$NODE_EXPORTER_URL"

rm -rf "/tmp/$NODE_EXPORTER_DIR" "/tmp/$NODE_EXPORTER_ARCHIVE"

wget --no-hsts "$NODE_EXPORTER_URL"
tar xvf "$NODE_EXPORTER_ARCHIVE"

echo "Останавливаем node_exporter перед обновлением файла..."
systemctl stop node_exporter 2>/dev/null || true
pkill -9 node_exporter 2>/dev/null || true
sleep 2

cp "$NODE_EXPORTER_DIR/node_exporter" /usr/local/bin/
chown root:root /usr/local/bin/node_exporter
chmod 755 /usr/local/bin/node_exporter

echo "node_exporter установлен в /usr/local/bin/node_exporter"

# ----------------------------------------------------------
# 4. Создание systemd-сервиса node_exporter
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 4. Настройка сервиса node_exporter"
echo "=========================================================="

cat > /etc/systemd/system/node_exporter.service <<EOF
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=root
Group=root
Type=simple
ExecStart=/usr/local/bin/node_exporter
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable node_exporter
systemctl restart node_exporter

echo "node_exporter запущен и добавлен в автозагрузку."

# ----------------------------------------------------------
# 5. Автоматическая настройка пароля VNC
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 5. Автоматическая настройка пароля VNC/noVNC"
echo "=========================================================="

mkdir -p "$USER_HOME/.vnc"
chown -R "$USERNAME:$USERNAME" "$USER_HOME/.vnc"

sudo -u "$USERNAME" x11vnc -storepasswd "$VNC_PASSWORD" "$USER_HOME/.vnc/passwd"

chown "$USERNAME:$USERNAME" "$USER_HOME/.vnc/passwd"
chmod 600 "$USER_HOME/.vnc/passwd"

echo "Пароль VNC/noVNC установлен автоматически."
echo "Файл пароля: $USER_HOME/.vnc/passwd"

# ----------------------------------------------------------
# 6. Создание systemd-сервиса x11vnc
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 6. Настройка сервиса x11vnc"
echo "=========================================================="

cat > /etc/systemd/system/x11vnc.service <<EOF
[Unit]
Description=Start x11vnc at startup
After=graphical.target multi-user.target
Requires=display-manager.service

[Service]
Type=simple
ExecStart=/usr/bin/x11vnc -forever -display :0 -rfbauth $USER_HOME/.vnc/passwd -rfbport $VNC_PORT
User=$USERNAME
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

systemctl daemon-reload
systemctl enable x11vnc.service

echo "x11vnc-сервис создан и добавлен в автозагрузку."

# ----------------------------------------------------------
# 7. Создание systemd-сервиса websockify/noVNC
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 7. Настройка сервиса websockify/noVNC"
echo "=========================================================="

cat > /etc/systemd/system/websockify.service <<EOF
[Unit]
Description=Websockify Service for noVNC
After=network.target x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
ExecStart=/usr/bin/websockify --web=/usr/share/novnc $NOVNC_PORT localhost:$VNC_PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable websockify.service

echo "websockify/noVNC-сервис создан и добавлен в автозагрузку."

# ----------------------------------------------------------
# 8. Запуск сервисов
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 8. Запуск сервисов"
echo "=========================================================="

systemctl restart node_exporter
systemctl restart x11vnc.service || true
systemctl restart websockify.service || true

echo "Сервисы запущены."

# ----------------------------------------------------------
# 9. Автоперенос папки kkt-tools в домашний каталог
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 9. Перенос папки kkt-tools в домашний каталог"
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_KKT_TOOLS="$SCRIPT_DIR/kkt-tools"
TARGET_KKT_TOOLS="$USER_HOME/kkt-tools"

if [ -d "$SOURCE_KKT_TOOLS" ]; then
  echo "Найдена папка kkt-tools:"
  echo "$SOURCE_KKT_TOOLS"

  if [ -d "$TARGET_KKT_TOOLS" ]; then
    echo "В домашней папке уже есть kkt-tools. Создаём резервную копию."
    BACKUP_DIR="$USER_HOME/kkt-tools_backup_$(date +%Y%m%d_%H%M%S)"
    mv "$TARGET_KKT_TOOLS" "$BACKUP_DIR"
    echo "Старая папка перенесена в:"
    echo "$BACKUP_DIR"
  fi

  cp -r "$SOURCE_KKT_TOOLS" "$TARGET_KKT_TOOLS"
  chown -R "$USERNAME:$USERNAME" "$TARGET_KKT_TOOLS"

  echo "Папка kkt-tools успешно скопирована в:"
  echo "$TARGET_KKT_TOOLS"
else
  echo "ВНИМАНИЕ: папка kkt-tools не найдена рядом со скриптом."
  echo "Ожидался путь:"
  echo "$SOURCE_KKT_TOOLS"
fi

# ----------------------------------------------------------
# 10. Определение IP-адреса
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 10. Определение IP-адреса"
echo "=========================================================="

IP_ADDRESS="$(hostname -I | awk '{print $1}')"

if [ -z "$IP_ADDRESS" ]; then
  IP_ADDRESS="IP-АДРЕС-МИНИПК"
fi

echo "IP-адрес устройства: $IP_ADDRESS"

# ----------------------------------------------------------
# 11. Финальная проверка
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " 11. Финальная проверка"
echo "=========================================================="

echo
echo "Проверка sudo без пароля:"
sudo -u "$USERNAME" sudo whoami || true

echo
echo "Статус node_exporter:"
systemctl is-active node_exporter || true

echo
echo "Статус x11vnc:"
systemctl is-active x11vnc.service || true

echo
echo "Статус websockify:"
systemctl is-active websockify.service || true

echo
echo "Проверка открытых портов:"
netstat -tlnp | grep -E "$VNC_PORT|$NOVNC_PORT|$NODE_EXPORTER_PORT" || true

echo
echo "Проверка метрик node_exporter:"
curl -s "http://localhost:$NODE_EXPORTER_PORT/metrics" | head || true

echo
echo "Проверка папки kkt-tools:"
ls -ld "$TARGET_KKT_TOOLS" || true

# ----------------------------------------------------------
# Итог
# ----------------------------------------------------------

echo
echo "=========================================================="
echo " Настройка завершена"
echo "=========================================================="
echo
echo "Что должно работать:"
echo
echo "1. sudo без пароля для пользователя:"
echo "   $USERNAME"
echo
echo "2. node_exporter:"
echo "   http://$IP_ADDRESS:$NODE_EXPORTER_PORT/metrics"
echo
echo "3. Удалённый рабочий стол через браузер noVNC:"
echo "   http://$IP_ADDRESS:$NOVNC_PORT/vnc.html"
echo
echo "4. Пароль VNC/noVNC:"
echo "   $VNC_PASSWORD"
echo
echo "5. Папка kkt-tools:"
echo "   $TARGET_KKT_TOOLS"
echo
echo "Порты:"
echo "- node_exporter: $NODE_EXPORTER_PORT"
echo "- x11vnc: $VNC_PORT"
echo "- noVNC/websockify: $NOVNC_PORT"
echo
