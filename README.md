# SNMP Monitor

Веб-приложение для мониторинга коммутаторов, маршрутизаторов, принтеров и
клиентов локальной сети. Backend работает на FastAPI, данные хранятся в
PostgreSQL, периодический опрос выполняет APScheduler, а production-интерфейс
публикуется через Nginx только по HTTPS.

Текущее состояние: код приложения подготовлен к контролируемому корпоративному
пилоту с чтением данных и ICMP/SNMP-мониторингом. Изменение конфигурации
реального оборудования через SNMP SET пока намеренно не реализовано.

## Стек

| Компонент | Реализация |
|---|---|
| Backend | Python 3.11, FastAPI |
| Frontend | HTML5, Bootstrap 5, JavaScript, DataTables |
| База данных | PostgreSQL 15, SQLAlchemy 2, Alembic |
| SNMP | EasySNMP / Net-SNMP |
| Авторизация | JWT, PBKDF2-SHA256, роли |
| Ping | `icmplib`, выполняется сервером |
| Фоновые задачи | APScheduler |
| Развёртывание | Docker Compose, Nginx, HTTPS |

## Состояние исходного плана

| Этап | Статус | Сделано | Для завершения |
|---|---|---|---|
| 1. Инфраструктура | Готово в коде | Docker Compose, PostgreSQL, Alembic, авторизация, роли, HTTPS и адаптивный корпоративный интерфейс | Создать целевую VM/сервер, сертификат и сетевые ACL; SSO/LDAP/MFA пока нет |
| 2. Интеграция | Частично | SNMP v1/v2c, ручное добавление v3, ICMP-автоопрос, SNMP-снимки портов, локальные Description/Access/Trunk | Проверить реальные модели, зафиксировать OID, добавить vendor-профили и расширенные варианты SNMPv3 |
| 3. Отображение | Частично | Устройства из БД, статус/скорость портов, PVID, FDB MAC, число MAC и IPv4 из ARP | Tagged VLAN, VLAN-aware FDB, IPv6 neighbors и vendor-specific OID |
| 4. Дополнительно | Частично | Страница принтеров, best-effort чтение одного расходника, настоящий серверный ping | Полный Printer-MIB: несколько расходников, нормированные проценты, ошибки, статус печати и MAC |
| 5. Уведомления | Начальный уровень | Опциональная односторонняя отправка Telegram при смене статуса устройства | Полноценный Telegram/Max-бот, команды, уведомления портов, PoE и перезапуск порта |

Статус выше описывает готовность кода, а не приёмку на конкретном оборудовании.
Автоматически проверяются миграции, авторизация и роли, защита нескольких
администраторов, production-настройки, планировщик и преобразование типовых
SNMP-ответов. Совместимость OID, качество данных Printer-MIB, ACL и поведение
под нагрузкой можно подтвердить только пилотом на корпоративных устройствах.

## Что работает сейчас

- JWT-вход, ограничение попыток входа и роли `admin`, `operator`, `viewer`;
- отключённая в production публичная регистрация;
- несколько администраторов и управление учётными записями;
- PostgreSQL-схема и последовательные Alembic-миграции;
- добавление, изменение и удаление контролируемых устройств;
- шифрование SNMP community и паролей v3 ключом Fernet;
- автоматический ICMP-опрос, история доступности и события смены статуса;
- реальный ping от имени сервера с потерями пакетов и средней задержкой;
- SNMP discovery v1/v2c в разрешённой подсети;
- ручное добавление SNMPv3 SHA/AES (`authNoPriv` или `authPriv`);
- чтение `sysName` и `sysDescr` во время обнаружения;
- чтение интерфейсов, состояния, скорости, PVID, FDB и IPv4 ARP;
- сохранение локального Description и метки Access/Trunk между опросами;
- отдельная страница принтеров;
- ICMP/ARP-поиск клиентов сети и необязательный LAN-агент для MAC/имён;
- поиск, фильтры, тёмная тема и интерфейс в стиле корпоративных Zyxel/HP;
- аудит действий, CSV-экспорт и настройка интервала опроса;
- HTTPS reverse proxy, production healthcheck, backup/restore scripts;
- тестовые профили без оборудования в development-режиме.

### Важные уточнения

- В таблице порта показываются изученные MAC из FDB, а не собственный
  физический MAC интерфейса коммутатора.
- Access/Trunk сейчас являются вычисляемой или локальной меткой. Это не
  изменяет конфигурацию коммутатора.
- Ping настоящий, но ответ показывается после завершения запроса; потоковый
  вывод каждой строки в реальном времени пока отсутствует.
- Планировщик сначала проверяет ICMP. Устройство, блокирующее ping, будет
  считаться offline, и его SNMP-опрос в этом цикле выполняться не будет.
- Маршрутизаторы пока проверяются только по ICMP. Плановый SNMP-опрос
  и сохранение телеметрии реализованы для коммутаторов и принтеров.
- Автоматический SNMP discovery требует ответа и на ICMP, и на SNMP и
  поддерживает только v1/v2c. SNMPv3-устройства добавляются вручную.
- `sysUpTime` запрашивается при discovery, но пока не сохраняется и не
  выводится. `ifAlias` используется только как эвристика начальной метки
  Access/Trunk.
- Значение расходника принтера читается из одного стандартного OID
  `prtMarkerSuppliesLevel`. Оно зависит от модели и не всегда является
  процентом. Ошибка чтения пока также сохраняется как `0`, поэтому её
  нельзя отличить от реально пустого расходника.
- Клиентский scan видит прежде всего отвечающие на ICMP узлы. Имя получается
  через reverse DNS, MAC — best effort из ARP контейнера. Для полных данных
  нужна L2-видимость LAN-агента либо будущая интеграция с DHCP/controller.
  Поле производителя уже есть в БД, но OUI/vendor enrichment сканер ещё не выполняет.

## Пользователи и администраторы

| Роль | Возможности |
|---|---|
| `viewer` | Просмотр устройств, портов, клиентов, принтеров, истории и CSV |
| `operator` | Всё из `viewer`, а также ping, scan/discovery, добавление и изменение устройств, ручное обновление SNMP-данных портов коммутатора и локальные метки портов |
| `admin` | Всё из `operator`, а также пользователи, параметры мониторинга, аудит и удаление устройств |

Поддерживается любое разумное количество администраторов. Первый `admin`
создаётся CLI-командой только в пустой базе. После входа он открывает
`Операции → Пользователи и роли` и может создавать дополнительные аккаунты с
ролью `admin`, `operator` или `viewer`.

Администратор может изменить у любой другой учётной записи:

- логин;
- email;
- пароль;
- роль;
- состояние «активен/заблокирован».

Это относится и к обычным пользователям, и к другому администратору.
Собственную запись через административную таблицу менять нельзя. Приложение
также не позволяет оставить систему без единственного активного
администратора. Смена пароля немедленно отзывает ранее выданные пользователю
JWT, а блокировка начинает действовать на следующем API-запросе.

Удаление пользователей и самостоятельная смена своего пароля пока не
реализованы. Для безопасной эксплуатации создайте минимум два admin-аккаунта.
После обновления со старой версии все ранее выданные JWT без привязки к паролю
станут недействительными — пользователям потребуется войти снова.

## Структура проекта

```text
backend/
  app/                  FastAPI, модели, маршруты, SNMP и планировщик
  alembic/              миграции PostgreSQL
  tests/                автоматические тесты
frontend/
  index.html            разметка
  styles.css            оформление
  app.js                клиентская логика
agent/
  lan_agent.py          необязательный сбор ARP/имён с L2-доступного хоста
deploy/nginx/            production-конфигурация HTTPS proxy
scripts/                 backup и restore
docker-compose.yml       локальная разработка
compose.production.yml   production backend + PostgreSQL
compose.tls.yml          production HTTPS proxy
```

## Локальный запуск

Нужны Docker Engine и Docker Compose plugin. Локальная конфигурация публикует
HTTP-порт `8000` и PostgreSQL `5432`, поэтому она предназначена только для
разработки в доверенной тестовой сети и не подходит для предприятия. Она не
передаёт `ALLOWED_NETWORKS` в backend, поэтому технически не ограничивает
целевые IP/CIDR: не запускайте её в чужой или корпоративной сети.

### 1. Подготовить `.env`

Если проект получается через Git:

```bash
git clone git@github.com:Porcupine15/SNMP_Monitor.git
cd SNMP_Monitor
```

Если проект уже скачан с GitHub как ZIP, распакуйте его и перейдите в каталог
с `docker-compose.yml`:

```bash
unzip SNMP_Monitor-RELEASE.zip
cd SNMP_Monitor-RELEASE
```

После получения исходников обоими способами:

```bash
cp .env.example .env
nano .env
```

Замените шаблонные значения. Секреты можно сгенерировать так:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Запишите четыре разных результата соответственно в `DB_PASSWORD`,
`SECRET_KEY`, `CREDENTIALS_ENCRYPTION_KEY` и `LAN_AGENT_TOKEN`. Файл `.env`
уже исключён из Git.

### 2. Запустить контейнеры

```bash
docker compose up -d --build
docker compose ps
docker compose logs backend --tail 50
curl --fail http://127.0.0.1:8000/api/health
```

Development Compose сам применяет миграции при старте backend.
Если healthcheck выполнен сразу после сборки и ещё не успел пройти,
дождитесь в логе `Application startup complete` и повторите `curl`.

### 3. Создать первого администратора

```bash
docker compose exec backend python -m app.bootstrap_admin \
  --username local-admin --email local-admin@example.test
```

Пароль длиной не менее 12 символов вводится дважды без отображения. Команда
работает только пока таблица пользователей пуста. Все последующие аккаунты,
включая дополнительные admin, создаются в Web-интерфейсе.

Откройте [http://localhost:8000](http://localhost:8000).

### 4. Логи, тесты и остановка

```bash
docker compose logs -f backend
docker compose exec -w /app -T backend pytest -q
docker compose down
```

`docker compose logs -f backend` продолжает показывать логи до `Ctrl+C`.
Команды тестов и остановки выполните после выхода из этого режима.

`docker compose down` сохраняет БД в volume. Команда ниже удаляет всю локальную
БД и допустима только для осознанного полного сброса стенда:

```bash
docker compose down -v
```

## Развёртывание на предприятии

Приложение устанавливается в отдельную Debian 12/13 VM или на отдельный
Debian-сервер. Если используется Proxmox, команды выполняются внутри гостевой
VM, а не на гипервизоре с приглашением `root@pve`. На самом Proxmox Docker для
этого проекта не нужен.

Для домашнего Proxmox и корпоративной установки должны быть разные база
данных, `.env`, JWT/Fernet-ключи, LAN-agent token и TLS-сертификаты. Домашние
устройства, community-строки, `.env` и дамп БД на предприятие не переносите.

### Требования к серверу

- 2 vCPU, 4 ГБ RAM, 32–40 ГБ диска для начального пилота;
- Debian 12/13 `amd64` (`x86_64`); текущие lock-файлы зависимостей
  подготовлены для Linux x86_64;
- постоянный IP и корпоративный FQDN;
- Docker Engine и Docker Compose plugin;
- `ca-certificates`, `curl`, `unzip`, `coreutils` и `python3`; Git нужен только
  для Git-варианта доставки;
- корпоративный TLS-сертификат и закрытый ключ;
- синхронизация времени и рабочий DNS;
- согласованные CIDR устройств и сетевые ACL;
- read-only SNMP-реквизиты, предпочтительно SNMPv3.

### 1. Получить зафиксированный релиз

Используйте согласованный tag или commit SHA, а не постоянно меняющуюся
ветку `main`. Выберите один из двух вариантов ниже.

#### Вариант A — клонирование Git

```bash
export REPOSITORY_URL='git@github.com:Porcupine15/SNMP_Monitor.git'
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
export SOURCE_DIR="$HOME/snmp-monitor-release"

git clone "$REPOSITORY_URL" "$SOURCE_DIR"
git -C "$SOURCE_DIR" checkout --detach "$RELEASE"
git -C "$SOURCE_DIR" rev-parse HEAD

sudo mkdir -m 755 /opt/snmp-monitor
git -C "$SOURCE_DIR" archive --format=tar HEAD \
  | sudo tar --extract --file=- --directory=/opt/snmp-monitor
sudo chown -R root:root /opt/snmp-monitor
sudo chmod -R go-w /opt/snmp-monitor
cd /opt/snmp-monitor
```

Выполняйте Git-команды от отдельной учётной записи развёртывания с read-only
deploy key в её `~/.ssh`, а не через `sudo git`: иначе Git будет искать ключ у
root. Если вы уже работаете как `root`, ключ должен находиться в `/root/.ssh`,
а `sudo` из команд нужно убрать. Перед установкой сравните результат
`rev-parse HEAD` с утверждённым полным SHA. Каталог в home является staging;
production-копия в `/opt` принадлежит root и не содержит `.git`.

#### Вариант B — перенос проверенного ZIP-архива

Этот вариант подходит, когда Git на целевом сервере недоступен или архив
переносится вручную. Скачивайте архив конкретного tag/commit, а не кнопку
`Download ZIP` изменяющейся ветки `main`.

На доверенном компьютере скачайте архив из GitHub или через браузер. Пример
для конкретного release:

```bash
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_FULL_SHA'
curl --fail --location \
  --output "SNMP_Monitor-${RELEASE}.zip" \
  "https://github.com/Porcupine15/SNMP_Monitor/archive/${RELEASE}.zip"
```

Для закрытого репозитория скачайте ZIP через уже аутентифицированный
браузер или утверждённый клиент. Не помещайте access token в URL или
команду shell: он может остаться в истории, логах и списке процессов.

Создайте контрольную сумму одной из команд:

```bash
# Linux
sha256sum "SNMP_Monitor-${RELEASE}.zip" \
  > "SNMP_Monitor-${RELEASE}.zip.sha256"

# macOS — используйте вместо предыдущей команды
shasum -a 256 "SNMP_Monitor-${RELEASE}.zip" \
  > "SNMP_Monitor-${RELEASE}.zip.sha256"
```

Передайте на сервер ZIP и файл `.sha256` согласованным способом. На Debian VM
для первой чистой установки:

```bash
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_FULL_SHA'
cd ~/transfer
sha256sum --check "SNMP_Monitor-${RELEASE}.zip.sha256"

export EXTRACT_DIR="$(mktemp -d)"
unzip -q "SNMP_Monitor-${RELEASE}.zip" -d "$EXTRACT_DIR"
sudo mkdir -m 755 /opt/snmp-monitor
sudo cp -a "$EXTRACT_DIR"/SNMP_Monitor-*/. /opt/snmp-monitor/
sudo chown -R root:root /opt/snmp-monitor
sudo chmod -R go-w /opt/snmp-monitor
sudo chmod 755 /opt/snmp-monitor/scripts/backup.sh \
  /opt/snmp-monitor/scripts/restore.sh
cd /opt/snmp-monitor
test -f compose.production.yml
test -f compose.tls.yml
test -f .env.example
test -f backend/Dockerfile
test -f backend/requirements.lock
test -f frontend/vendor/bootstrap/bootstrap.bundle.min.js
test -x scripts/backup.sh
test -x scripts/restore.sh
```

Если `unzip` отсутствует, установите его из корпоративного репозитория либо
заранее включите в образ VM. Файл `.sha256`, созданный рядом с ZIP,
защищает от повреждения при переносе, но сам по себе не доказывает
подлинность. Для этого сверьте точный tag/полный commit SHA и, если есть,
опубликованную SHA-256 или подпись через отдельный доверенный канал.
Полный SHA релиза и SHA-256 ZIP зафиксируйте в заявке на изменение.

GitHub ZIP содержит только файлы репозитория: в нём нет домашней `.env`, базы
PostgreSQL, Docker volume и локальных `backups/`. Не создавайте ZIP всего
рабочего каталога вручную. В архивной установке также нет каталога `.git`,
поэтому обновлять production-каталог командами `git fetch`/`git checkout`
нельзя. Команды обоих вариантов рассчитаны на чистую первую установку:
`/opt/snmp-monitor` до их выполнения не должен существовать.

Одного ZIP с исходниками недостаточно для полностью изолированного сервера:
Compose должен ещё получить Docker-образы, а сборка backend — Debian-пакеты и
Python wheels. Проверенный standalone offline-пакет пока не поставляется:
используйте контролируемый доступ к корпоративным registry/APT/PyPI-зеркалам
или сначала реализуйте и примите отдельный offline-вариант по
[CORPORATE_DEPLOYMENT.md](CORPORATE_DEPLOYMENT.md).

### 2. Создать новый production `.env`

```bash
sudo install -o root -g root -m 600 .env.example .env
sudoedit .env
```

Если вы уже вошли как `root` и `sudo` не установлен, уберите `sudo` из первой
команды, а файл откройте как `nano .env` или `vi .env`.

Сгенерируйте на целевом сервере четыре независимых значения:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # DB_PASSWORD
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'  # SECRET_KEY
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'  # CREDENTIALS_ENCRYPTION_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'  # LAN_AGENT_TOKEN
```

Обязательно задайте:

- уникальные `DB_PASSWORD`, `SECRET_KEY`, `CREDENTIALS_ENCRYPTION_KEY` и
  `LAN_AGENT_TOKEN`;
- `ENVIRONMENT=production`;
- `ACCESS_TOKEN_EXPIRE_MINUTES=60` — допустимый production-диапазон 5–120;
- точные согласованные сети в `ALLOWED_NETWORKS`, без `0.0.0.0/0` и `::/0`;
- FQDN, IP сервера, `localhost` и `127.0.0.1` в `TRUSTED_HOSTS`;
- IP сервера в `TLS_BIND_ADDRESS`;
- абсолютные `TLS_CERT_PATH` и `TLS_KEY_PATH`;
- `ALLOW_PUBLIC_REGISTRATION=false`.

`CORS_ORIGINS` оставьте пустым при Web-интерфейсе с того же FQDN. Если он
нужен, production принимает только явные HTTPS origins.

### 3. Установить TLS-сертификат

Пример каталогов; имена исходных файлов замените своими:

```bash
sudo install -d -o root -g root -m 750 /etc/snmp-monitor/tls
sudo install -o root -g root -m 640 server.crt /etc/snmp-monitor/tls/server.crt
sudo install -o root -g root -m 600 server.key /etc/snmp-monitor/tls/server.key
```

На предприятии сертификат должен быть выдан доверенным корпоративным CA.
Файл `server.crt` должен содержать серверный сертификат и необходимые
промежуточные сертификаты. Корневой CA добавьте в хранилище доверия
Debian VM и клиентских ПК. Если системное хранилище ещё не настроено, для
проверки используйте `curl --cacert /path/to/corporate-root-ca.crt ...`, а не
`--insecure`.
Самоподписанный сертификат и `curl --insecure` допустимы только на домашнем
тестовом стенде.

### 4. Первый запуск

```bash
cd /opt/snmp-monitor
export FQDN='snmp-monitor.corp.example'
export ADMIN_USERNAME='snmp-admin'
export ADMIN_EMAIL='snmp-admin@corp.example'

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

Если в БД уже существует хотя бы один пользователь, не запускайте bootstrap:
команда завершится ошибкой, а дополнительные аккаунты создаются через
Web-интерфейс. Backend доступен на loopback VM, PostgreSQL наружу не
публикуется, а пользователи заходят только через `https://<FQDN>/`.

### 5. Сетевые разрешения для пилота

Минимально согласуйте:

- входящий TCP/443 к серверу только из пользовательских/административных сетей;
- SSH только из management-сети;
- исходящий ICMP и UDP/161 от VM к утверждённым устройствам;
- DNS и NTP;
- исходящий TCP/443 к Docker registry и PyPI, а также TCP/80/443 к
  настроенным Debian APT-зеркалам на время
  online-сборки, а также к Git-серверу при HTTPS-доставке;
- исходящий TCP/22 к GitHub, если репозиторий клонируется по SSH;
- исходящий TCP/443 к Telegram API только если включены уведомления;
- ACL на устройствах: SNMP только от IP этой VM и только read-only.

Не открывайте наружу TCP/8000 и TCP/5432. Порт Proxmox `8006` не относится к
приложению и должен оставаться в отдельном management-контуре.

### 6. Приёмочная проверка

1. Войдите первым admin и создайте второго admin.
2. Создайте тестовых `operator` и `viewer`, проверьте ограничения ролей.
3. Измените у тестового пользователя email/роль/пароль и проверьте повторный вход.
4. Добавьте один пилотный коммутатор с read-only SNMP.
5. Проверьте server-side ping, ручное обновление SNMP-данных портов и сохранение Description.
6. Проверьте, что адрес вне `ALLOWED_NETWORKS` отклоняется.
7. Создайте и проверьте резервную копию.

```bash
cd /opt/snmp-monitor
sudo ./scripts/backup.sh
```

Скрипт создаёт и проверяет локальный dump в `/opt/snmp-monitor/backups`.
Отдельно настройте его зашифрованное копирование вне VM, срок хранения,
мониторинг ошибок и пробное восстановление на отдельном стенде.

Полный чек-лист подготовки, firewall, offline-доставки, пилота, обновления и
отката приведён в [CORPORATE_DEPLOYMENT.md](CORPORATE_DEPLOYMENT.md).
Сокращённая инструкция для Debian VM на Proxmox находится в
[DEPLOYMENT.md](DEPLOYMENT.md).

## Обновление production

Production-каталог `/opt/snmp-monitor` принадлежит root и не обновляется
командой `git pull`. Новый релиз сначала готовится рядом в
`/opt/snmp-monitor-next`. Перед началом создайте backup и зафиксируйте
точный image работающего backend:

```bash
cd /opt/snmp-monitor
export ROLLBACK_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export BACKUP_OUTPUT="$(sudo ./scripts/backup.sh)" || exit 1
printf '%s\n' "$BACKUP_OUTPUT"
export ROLLBACK_DUMP="${BACKUP_OUTPUT#Backup created and verified: }"
test "$ROLLBACK_DUMP" != "$BACKUP_OUTPUT" || exit 1
sudo test -f "$ROLLBACK_DUMP" || exit 1
sudo sh -c 'cd "$(dirname "$1")" && sha256sum --check "$(basename "$1").sha256"' \
  sh "$ROLLBACK_DUMP" || exit 1

export CURRENT_BACKEND_IMAGE="$(sudo docker inspect --format '{{.Image}}' snmp_backend)"
export ROLLBACK_IMAGE="snmp-monitor-backend:rollback-${ROLLBACK_ID}"
test -n "$ROLLBACK_DUMP"
sudo docker image tag "$CURRENT_BACKEND_IMAGE" "$ROLLBACK_IMAGE"
printf 'ROLLBACK_ID=%s\nROLLBACK_DUMP=%s\nROLLBACK_IMAGE=%s\n' \
  "$ROLLBACK_ID" "$ROLLBACK_DUMP" "$ROLLBACK_IMAGE"
```

Запишите три выведенных значения в заявку на изменение. Не выполняйте
`docker image prune` до завершения периода наблюдения. Если shell-сессия
прервётся, перед продолжением восстановите эти переменные из записи.

Каталог `/opt/snmp-monitor-next` перед подготовкой не должен существовать.
Если он остался от неудачной попытки, сначала проверьте его содержимое и только
после этого очистите или переименуйте его.

### Подготовка обновления из Git

Git используется только в staging-каталоге deploy-пользователя:

```bash
export NEW_RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
export SOURCE_DIR="$HOME/snmp-monitor-release"

git -C "$SOURCE_DIR" fetch --tags --prune
git -C "$SOURCE_DIR" checkout --detach "$NEW_RELEASE"
git -C "$SOURCE_DIR" rev-parse HEAD

sudo mkdir -m 755 /opt/snmp-monitor-next
git -C "$SOURCE_DIR" archive --format=tar HEAD \
  | sudo tar --extract --file=- --directory=/opt/snmp-monitor-next
```

Перед продолжением сравните вывод `rev-parse HEAD` с утверждённым полным SHA.
Если staging-каталог был удалён, сначала заново выполните `git clone` из
варианта A первоначальной установки, но не копируйте его прямо поверх `/opt`.

### Подготовка обновления из ZIP

Сначала проверьте ZIP и `.sha256` по инструкции первоначальной установки,
затем распакуйте новый релиз в новый временный каталог:

```bash
export NEW_RELEASE='REPLACE_WITH_APPROVED_TAG_OR_FULL_SHA'
cd ~/transfer
sha256sum --check "SNMP_Monitor-${NEW_RELEASE}.zip.sha256"

export EXTRACT_DIR="$(mktemp -d)"
unzip -q "SNMP_Monitor-${NEW_RELEASE}.zip" -d "$EXTRACT_DIR"
sudo mkdir -m 755 /opt/snmp-monitor-next
sudo cp -a "$EXTRACT_DIR"/SNMP_Monitor-*/. /opt/snmp-monitor-next/
```

### Общая проверка и предварительная сборка

Сохраните действующий `.env` и backup. ZIP не сохраняет executable bit,
поэтому права скриптов задаются явно и безопасно повторяются для Git-варианта:

```bash
sudo cp -a /opt/snmp-monitor/.env /opt/snmp-monitor-next/.env
sudo cp -a /opt/snmp-monitor/backups /opt/snmp-monitor-next/backups
sudo chown -R root:root /opt/snmp-monitor-next
sudo chmod -R go-w /opt/snmp-monitor-next
sudo chmod 755 /opt/snmp-monitor-next/scripts/backup.sh \
  /opt/snmp-monitor-next/scripts/restore.sh
test -x /opt/snmp-monitor-next/scripts/backup.sh
test -x /opt/snmp-monitor-next/scripts/restore.sh

diff -u /opt/snmp-monitor/.env.example \
  /opt/snmp-monitor-next/.env.example || true
sudoedit /opt/snmp-monitor-next/.env
```

Перенесите новые параметры в сохранённый `.env` вручную, не заменяя
действующие секреты шаблонными значениями. Затем проверьте Compose,
соберите новый image под фиксированным именем project и проверьте его импорт. Всё
это выполняется до остановки текущего backend:

```bash
cd /opt/snmp-monitor-next
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml config --quiet
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml build backend
sudo docker run --rm snmp-monitor-backend:latest \
  python -c 'import app.main; print("backend import ok")'
```

Не переходите к переключению, если любая из этих команд завершилась с ошибкой.
Если обновление на этом прервано, верните рабочий тег командой
`sudo docker image tag "$ROLLBACK_IMAGE" snmp-monitor-backend:latest`.

### Переключение и миграция

```bash
cd /opt/snmp-monitor
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml stop proxy backend

cd /opt
export PREVIOUS_DIR="/opt/snmp-monitor-previous-${ROLLBACK_ID:?restore ROLLBACK_ID}"
sudo mv /opt/snmp-monitor "$PREVIOUS_DIR"
sudo mv /opt/snmp-monitor-next /opt/snmp-monitor
printf 'PREVIOUS_DIR=%s\n' "$PREVIOUS_DIR"

cd /opt/snmp-monitor
export FQDN='snmp-monitor.corp.example'
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml up -d backend proxy
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml ps
curl --fail "https://${FQDN}/api/health"
```

Запишите `PREVIOUS_DIR` в заявку. До завершения приёмки не удаляйте этот каталог,
образ с тегом `ROLLBACK_IMAGE` и дамп. `CREDENTIALS_ENCRYPTION_KEY` храните
отдельно от дампа в менеджере секретов: без него SNMP-реквизиты восстановить нельзя.

### Откат после несовместимой миграции

Если миграция изменила схему и требуется откат, верните все три части:
каталог кода, точный backend image и предобновленческую БД. В новой shell-сессии
сначала восстановите из заявки `ROLLBACK_ID`, `ROLLBACK_DUMP`, `ROLLBACK_IMAGE` и
`PREVIOUS_DIR`, затем:

```bash
test -n "$ROLLBACK_ID" && test -n "$ROLLBACK_DUMP" \
  && test -n "$ROLLBACK_IMAGE" && test -n "$PREVIOUS_DIR"
sudo test -f "$ROLLBACK_DUMP"
sudo test -d "$PREVIOUS_DIR"
sudo docker image inspect "$ROLLBACK_IMAGE"

cd /opt/snmp-monitor
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml stop proxy backend

cd /opt
export FAILED_DIR="/opt/snmp-monitor-failed-${ROLLBACK_ID}"
sudo mv /opt/snmp-monitor "$FAILED_DIR"
sudo mv "$PREVIOUS_DIR" /opt/snmp-monitor
sudo docker image tag "$ROLLBACK_IMAGE" snmp-monitor-backend:latest

cd /opt/snmp-monitor
export FQDN='snmp-monitor.corp.example'
sudo ./scripts/restore.sh "$ROLLBACK_DUMP"
sudo docker compose -p snmp-monitor \
  -f compose.production.yml -f compose.tls.yml ps
curl --fail "https://${FQDN}/api/health"
```

`restore.sh` попросит ввести `RESTORE`, затем заменит текущую БД дампом и
поднимет старые backend/proxy. Каталог `FAILED_DIR` сохраните для разбора причины.

## Диагностика

```bash
sudo docker compose -f compose.production.yml -f compose.tls.yml ps
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  logs backend --tail 150
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  logs proxy --tail 100
```

Если backend перезапускается с ошибкой
`ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 120`, установите в `.env`
значение `60` и снова выполните `up -d backend proxy`. Proxy запускается только
после перехода backend в состояние `healthy`.

## Что ещё предстоит сделать

### До корпоративного пилота

- выделить чистую Debian VM/сервер с постоянным IP и FQDN;
- согласовать `ALLOWED_NETWORKS`, firewall и read-only SNMP ACL;
- создать отдельные production-секреты, чистую БД и корпоративный TLS;
- согласовать доступ к внутренним registry/APT/PyPI-зеркалам; для
  полностью изолированной VM сначала подготовить и принять offline-артефакт;
- создать минимум два admin-аккаунта и проверить роли на тестовых пользователях;
- настроить зашифрованную внешнюю копию dump, срок хранения и пробное
  восстановление до ввода реальных реквизитов;
- начать с одного согласованного коммутатора и одного принтера;
- сверить фактические OID/PVID/FDB/ARP/Printer-MIB с Web-интерфейсом;
- зафиксировать критерии приёмки, окно наблюдения и процедуру отката.

### После пилота и получения моделей оборудования

- добавить vendor-профили оборудования;
- добавить SNMP-телеметрию маршрутизаторов;
- реализовать tagged VLAN, VLAN-aware FDB и IPv6 neighbor table;
- корректно нормировать расходники и читать состояние/ошибки принтеров;
- интегрироваться с DHCP, Wi-Fi controller или NAC для полного списка клиентов;
- добавить OUI/vendor enrichment для обнаруженных MAC-адресов;
- добавить SNMP traps;
- реализовать SNMP SET только после отдельной модели прав, dry-run и аудита;
- добавить реальное управление VLAN/Trunk/Access, PoE и перезапуском порта;
- создать полноценного Telegram/Max-бота с командами;
- добавить удаление пользователей и безопасную самостоятельную смену пароля;
- при необходимости внедрить LDAP/AD/SSO, MFA, HA и внешний планировщик.

До появления внешнего планировщика production должен запускаться в одном
экземпляре: каждый процесс приложения содержит собственный APScheduler.
