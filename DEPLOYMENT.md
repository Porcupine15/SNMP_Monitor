# Развёртывание на Proxmox

Приложение запускается в отдельной Debian VM. На хост Proxmox Docker и
исходный код устанавливать не нужно.

Для производственной корпоративной сети используйте полную инструкцию
[CORPORATE_DEPLOYMENT.md](CORPORATE_DEPLOYMENT.md). Она содержит обязательные
ACL, HTTPS, чистое создание секретов и БД, пилот SNMP, backup/restore и откат.

## Требования к VM

- Debian 12/13 amd64 без графического окружения;
- 2 vCPU, 4 ГБ RAM, 32–40 ГБ диска;
- сетевой адаптер VirtIO, подключённый к `vmbr0`;
- постоянный адрес в локальной сети;
- Docker Engine и Docker Compose plugin.

## Получение проекта

Разворачивайте зафиксированный tag или commit, а не изменяющуюся ветку:

```bash
export REPOSITORY_URL='git@github.com:Porcupine15/SNMP_Monitor.git'
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
sudo git clone "$REPOSITORY_URL" /opt/snmp-monitor
cd /opt/snmp-monitor
sudo git checkout --detach "$RELEASE"
sudo chown -R root:root /opt/snmp-monitor
```

Для закрытого репозитория используйте отдельный read-only deploy key, а не
пароль от основной учётной записи.

## Переменные окружения

Создавайте новый `.env` на целевой VM. Домашний `.env` и домашнюю БД в
корпоративную среду переносить нельзя.

```bash
sudo install -o root -g root -m 600 .env.example .env
sudoedit .env
```

Сгенерируйте четыре независимых значения:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # DB_PASSWORD
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'  # SECRET_KEY
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'  # CREDENTIALS_ENCRYPTION_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # LAN_AGENT_TOKEN
```

Запишите их в `.env` соответственно как `DB_PASSWORD`, `SECRET_KEY`,
`CREDENTIALS_ENCRYPTION_KEY` и `LAN_AGENT_TOKEN`. Не коммитьте и не
пересылайте содержимое `.env`.

Также заполните `ENVIRONMENT=production`, точные `ALLOWED_NETWORKS`,
`TRUSTED_HOSTS`, пути TLS-сертификата/ключа и оставьте
`ALLOW_PUBLIC_REGISTRATION=false`. Полный пример есть в корпоративной
инструкции.

## Первый запуск

Production-интерфейс публикуется только по HTTPS через `compose.tls.yml`.
Сначала запускается PostgreSQL, затем явно применяется Alembic, интерактивно
создаётся первый администратор и только после этого запускаются backend и
reverse proxy:

```bash
export ADMIN_USERNAME='snmp-admin'
export ADMIN_EMAIL='snmp-admin@corp.example'
export FQDN='snmp-monitor.corp.example'
sudo docker compose -f compose.production.yml -f compose.tls.yml config --quiet
sudo docker compose -f compose.production.yml -f compose.tls.yml build backend
sudo docker compose -f compose.production.yml -f compose.tls.yml up -d db
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  run --rm backend python -m app.bootstrap_admin \
  --username "$ADMIN_USERNAME" --email "$ADMIN_EMAIL"
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
sudo docker compose -f compose.production.yml -f compose.tls.yml ps
curl --fail "https://${FQDN}/api/health"
```

Пароль bootstrap-admin вводится дважды без отображения. Интерфейс доступен
только по `https://<КОРПОРАТИВНЫЙ_FQDN>/`; порт 8000 остаётся привязанным к
loopback VM, а PostgreSQL наружу не публикуется.

## Обновление

Сначала сделайте и проверьте резервную копию, затем загрузите зафиксированный
релиз, остановите Web-компоненты и явно примените миграцию:

```bash
cd /opt/snmp-monitor
export NEW_RELEASE='REPLACE_WITH_NEW_TAG_OR_SHA'
sudo ./scripts/backup.sh
sudo git fetch --tags --prune
sudo git checkout --detach "$NEW_RELEASE"
sudo docker compose -f compose.production.yml -f compose.tls.yml build backend
sudo docker compose -f compose.production.yml -f compose.tls.yml stop proxy backend
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
sudo docker compose -f compose.production.yml -f compose.tls.yml ps
```

При откате после изменения схемы верните не только предыдущий код/image, но и
предобновленческий дамп. Точная последовательность описана в
[CORPORATE_DEPLOYMENT.md](CORPORATE_DEPLOYMENT.md#12-откат).

## Важные данные

Для полного восстановления нужны:

- дамп PostgreSQL;
- файл `.env`, особенно `CREDENTIALS_ENCRYPTION_KEY`;
- исходный код из Git;
- резервная копия VM средствами Proxmox.

Порт PostgreSQL в production-конфигурации не публикуется в локальную сеть.
Порты `8000` и `5432` не открывайте через firewall. TCP/443 и SSH разрешайте
только из согласованных административных сетей; Proxmox `8006` не относится к
приложению и также должен оставаться в отдельном management-контуре.
