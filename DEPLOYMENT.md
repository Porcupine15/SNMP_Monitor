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

Актуальные варианты доставки зафиксированного релиза через Git или
проверенный ZIP описаны в [README.md](README.md#1-получить-зафиксированный-релиз). В обоих
случаях релиз сначала проверяется в staging, а production-копия устанавливается
в `/opt/snmp-monitor` как `root:root` без `.git`. Не клонируйте рабочее Git-дерево
непосредственно в `/opt`.

## Переменные окружения

Создавайте новый `.env` на целевой VM. Домашний `.env` и домашнюю БД в
корпоративную среду переносить нельзя.

```bash
cd /opt/snmp-monitor
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
cd /opt/snmp-monitor
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

Единая актуальная процедура для Git- и ZIP-релизов приведена в
[README.md](README.md#обновление-production). Она сохраняет дамп, тегирует точный
предыдущий backend image, собирает новый image до остановки и описывает
возврат кода, image и БД. Не используйте `git fetch`/`git checkout` в
`/opt/snmp-monitor`: production-каталог не содержит `.git`.

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
