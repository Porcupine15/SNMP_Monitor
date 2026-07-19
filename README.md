# SNMP Monitor

Веб-приложение для мониторинга коммутаторов, маршрутизаторов, принтеров и
клиентов локальной сети. Backend работает на FastAPI, данные хранятся в
PostgreSQL, периодический опрос выполняет APScheduler, а production-интерфейс
публикуется через Nginx только по HTTPS.

Текущее состояние: приложение подходит для контролируемого корпоративного
пилота с чтением данных и ICMP/SNMP-мониторингом. Изменение конфигурации
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

| Этап | Сделано | Осталось |
|---|---|---|
| 1. Инфраструктура | Docker Compose, PostgreSQL, Alembic, авторизация, роли, адаптивный корпоративный интерфейс | Саму VM/сервер и сетевые ACL создаёт администратор инфраструктуры; SSO/LDAP/MFA пока нет |
| 2. Интеграция | SNMP v1/v2c, ручное добавление v3, ICMP-автоопрос, SNMP-снимки портов, локальные Description/Access/Trunk | Проверка на реальных моделях, vendor-профили и расширенные варианты SNMPv3 |
| 3. Отображение | Устройства из БД, статус/скорость портов, PVID, FDB MAC, число MAC и IPv4 из ARP | Tagged VLAN, VLAN-aware FDB, IPv6 neighbors и vendor-specific OID |
| 4. Дополнительно | Страница принтеров, best-effort чтение одного расходника, настоящий серверный ping | Полный Printer-MIB: несколько расходников, нормированные проценты, ошибки, статус печати и MAC |
| 5. Уведомления | Опциональная односторонняя отправка Telegram при смене статуса устройства | Полноценный Telegram/Max-бот, команды, уведомления портов, PoE и перезапуск порта |

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
- Автоматический SNMP discovery требует ответа и на ICMP, и на SNMP и
  поддерживает только v1/v2c. SNMPv3-устройства добавляются вручную.
- `sysUpTime` запрашивается при discovery, но пока не сохраняется и не
  выводится. `ifAlias` используется только как эвристика начальной метки
  Access/Trunk.
- Значение расходника принтера читается из одного стандартного OID
  `prtMarkerSuppliesLevel`. Оно зависит от модели и не всегда является
  процентом.
- Клиентский scan видит прежде всего отвечающие на ICMP узлы. Имя получается
  через reverse DNS, MAC — best effort из ARP контейнера. Для полных данных
  нужна L2-видимость LAN-агента либо будущая интеграция с DHCP/controller.

## Пользователи и администраторы

| Роль | Возможности |
|---|---|
| `viewer` | Просмотр устройств, портов, клиентов, принтеров, истории и CSV |
| `operator` | Всё из `viewer`, а также ping, scan/discovery, добавление и изменение устройств, ручной SNMP-опрос и локальные метки портов |
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

```bash
git clone git@github.com:Porcupine15/SNMP_Monitor.git
cd SNMP_Monitor
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
curl --fail http://127.0.0.1:8000/api/health
```

Development Compose сам применяет миграции при старте backend.

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
- постоянный IP и корпоративный FQDN;
- Docker Engine и Docker Compose plugin;
- корпоративный TLS-сертификат и закрытый ключ;
- синхронизация времени и рабочий DNS;
- согласованные CIDR устройств и сетевые ACL;
- read-only SNMP-реквизиты, предпочтительно SNMPv3.

### 1. Получить зафиксированный релиз

Используйте согласованный tag или commit SHA, а не постоянно меняющуюся
ветку `main`:

```bash
export REPOSITORY_URL='git@github.com:Porcupine15/SNMP_Monitor.git'
export RELEASE='REPLACE_WITH_APPROVED_TAG_OR_SHA'
sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/snmp-monitor
git clone "$REPOSITORY_URL" /opt/snmp-monitor
cd /opt/snmp-monitor
git checkout --detach "$RELEASE"
```

Выполняйте Git-команды от отдельной учётной записи развёртывания с read-only
deploy key в её `~/.ssh`, а не через `sudo git`: иначе Git будет искать ключ у
root. Если вы уже работаете как `root`, ключ должен находиться в `/root/.ssh`,
а `sudo` из команд нужно убрать.

### 2. Создать новый production `.env`

```bash
sudo install -o root -g root -m 600 .env.example .env
sudoedit .env
```

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
- точные согласованные сети в `ALLOWED_NETWORKS`, без `0.0.0.0/0`;
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
- исходящий TCP/443 к Docker registry и Git-серверу на время online-установки
  и обновления либо заранее подготовленную offline-доставку;
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
5. Проверьте server-side ping, ручной SNMP-опрос и сохранение Description.
6. Проверьте, что адрес вне `ALLOWED_NETWORKS` отклоняется.
7. Создайте и проверьте резервную копию.

```bash
cd /opt/snmp-monitor
sudo ./scripts/backup.sh
```

Полный чек-лист подготовки, firewall, offline-доставки, пилота, обновления и
отката приведён в [CORPORATE_DEPLOYMENT.md](CORPORATE_DEPLOYMENT.md).
Сокращённая инструкция для Debian VM на Proxmox находится в
[DEPLOYMENT.md](DEPLOYMENT.md).

## Обновление production

Перед каждым обновлением сделайте backup, затем установите утверждённый tag/SHA,
пересоберите backend, примените миграции и поднимите сервисы:

```bash
cd /opt/snmp-monitor
export NEW_RELEASE='REPLACE_WITH_NEW_TAG_OR_SHA'
sudo ./scripts/backup.sh
git fetch --tags --prune
git checkout --detach "$NEW_RELEASE"
sudo docker compose -f compose.production.yml -f compose.tls.yml build backend
sudo docker compose -f compose.production.yml -f compose.tls.yml stop proxy backend
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  run --rm backend alembic -c alembic.ini upgrade head
sudo docker compose -f compose.production.yml -f compose.tls.yml \
  up -d backend proxy
sudo docker compose -f compose.production.yml -f compose.tls.yml ps
```

При несовместимом откате схемы возвращаются и предыдущий код/image, и дамп,
созданный перед обновлением. `CREDENTIALS_ENCRYPTION_KEY` храните отдельно от
дампа в менеджере секретов: без него SNMP-реквизиты восстановить нельзя.

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

- провести SNMP-пилот на реальных корпоративных моделях и зафиксировать OID;
- добавить vendor-профили оборудования;
- реализовать tagged VLAN, VLAN-aware FDB и IPv6 neighbor table;
- корректно нормировать расходники и читать состояние/ошибки принтеров;
- интегрироваться с DHCP, Wi-Fi controller или NAC для полного списка клиентов;
- добавить SNMP traps;
- реализовать SNMP SET только после отдельной модели прав, dry-run и аудита;
- добавить реальное управление VLAN/Trunk/Access, PoE и перезапуском порта;
- создать полноценного Telegram/Max-бота с командами;
- добавить удаление пользователей и безопасную самостоятельную смену пароля;
- при необходимости внедрить LDAP/AD/SSO, MFA, HA и внешний планировщик.

До появления внешнего планировщика production должен запускаться в одном
экземпляре: каждый процесс приложения содержит собственный APScheduler.
