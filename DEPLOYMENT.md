# Развёртывание на Proxmox

Приложение запускается в отдельной Debian VM. На хост Proxmox Docker и
исходный код устанавливать не нужно.

## Требования к VM

- Debian 13 amd64 без графического окружения;
- 2 vCPU, 4 ГБ RAM, 32–40 ГБ диска;
- сетевой адаптер VirtIO, подключённый к `vmbr0`;
- постоянный адрес в локальной сети;
- Docker Engine и Docker Compose plugin.

## Получение проекта

Создайте каталог от имени пользователя, который будет выполнять развёртывание:

```bash
sudo install -d -o "$USER" -g "$USER" /opt/snmp-monitor
git clone <URL_РЕПОЗИТОРИЯ> /opt/snmp-monitor
cd /opt/snmp-monitor
```

Для закрытого репозитория используйте отдельный read-only deploy key, а не
пароль от основной учётной записи.

## Переменные окружения

```bash
cp .env.example .env
chmod 600 .env
```

Сгенерируйте три независимых значения:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Запишите их в `.env` соответственно как `SECRET_KEY`,
`CREDENTIALS_ENCRYPTION_KEY` и `LAN_AGENT_TOKEN`. Также замените
`DB_PASSWORD`. Не коммитьте и не пересылайте содержимое `.env`.

## Первый запуск

```bash
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml up -d --build
docker compose -f compose.production.yml ps
docker compose -f compose.production.yml logs backend --tail 100
curl --fail http://127.0.0.1:8000/api/health
```

Миграции Alembic применяются контейнером backend перед запуском приложения.
Интерфейс будет доступен по адресу `http://<IP_VM>:8000`.

## Обновление

Сначала сделайте резервную копию базы, затем загрузите новую версию:

```bash
cd /opt/snmp-monitor
mkdir -p backups
set -a; . ./.env; set +a
docker compose -f compose.production.yml exec -T db \
  pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "backups/snmp-$(date +%F-%H%M%S).dump"
git pull --ff-only
docker compose -f compose.production.yml up -d --build
docker compose -f compose.production.yml ps
```

Альтернатива загрузке `.env` в текущую оболочку — подставить имя пользователя
и базы в команду `pg_dump` явно.

## Важные данные

Для полного восстановления нужны:

- дамп PostgreSQL;
- файл `.env`, особенно `CREDENTIALS_ENCRYPTION_KEY`;
- исходный код из Git;
- резервная копия VM средствами Proxmox.

Порт PostgreSQL в production-конфигурации не публикуется в локальную сеть.
Не настраивайте проброс портов `8000`, `5432`, `22` или `8006` на домашнем
роутере без отдельного VPN и правил доступа.
