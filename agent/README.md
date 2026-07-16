# LAN agent

Запускается на Mac/Linux в домашней сети и передаёт локальную ARP-таблицу в
SNMP Monitor. Не использует пароль Wi-Fi или роутера.

```bash
export LAN_AGENT_TOKEN='значение LAN_AGENT_TOKEN из .env'
python3 lan_agent.py
```

Для постоянного обновления раз в минуту:

```bash
python3 lan_agent.py --watch --interval 60
```

Агент должен запускаться на том же Mac, где работает Docker, или использовать
`SNMP_MONITOR_URL` с адресом backend. Перед запуском веб-сканирования полезно
наполнить ARP-таблицу; после этого агент сохранит найденные MAC и имена.
