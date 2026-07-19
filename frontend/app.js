        const API_BASE = '/api';
        let currentUser = null;
        let currentPage = 'dashboard';
        let devicesTable = null;
        let printersTable = null;
        let isLoginMode = true;
        let cachedDevices = new Map();
        let clientItems = [];
        let managedUsers = [];
        let pingDefaults = { count: 3, timeout: 2 };

        const PAGE_META = {
            dashboard: ['Сводка сети', 'Текущее состояние контролируемой инфраструктуры'],
            devices: ['Устройства', 'Управляемое оборудование и его доступность'],
            clients: ['Клиенты сети', 'Обнаруженные клиенты Wi‑Fi и Ethernet'],
            printers: ['Принтеры', 'Состояние печати и расходных материалов'],
            settings: ['Обнаружение и лаборатория', 'Добавление оборудования и тестовые профили'],
            operations: ['Операции', 'Параметры мониторинга, экспорт и аудит'],
            ports: ['Интерфейсы устройства', 'Сохранённый снимок портов, VLAN, FDB и ARP'],
            lab: ['Лабораторный профиль', 'Детерминированные данные без обращения к сети']
        };

        async function configureRegistration() {
            const link = document.getElementById('toggleRegisterLink');
            if (!link) return;
            link.hidden = true;
            try {
                const response = await fetch(`${API_BASE}/auth/registration-status`);
                if (!response.ok) return;
                const data = await response.json();
                link.hidden = !data.enabled;
            } catch (_) {
                link.hidden = true;
            }
        }

        // ---------- Переключение форм ----------
        document.getElementById('toggleRegisterLink')?.addEventListener('click', function(e) {
            e.preventDefault();
            isLoginMode = !isLoginMode;
            document.getElementById('loginForm').style.display = isLoginMode ? 'block' : 'none';
            document.getElementById('registerForm').style.display = isLoginMode ? 'none' : 'block';
            document.getElementById('loginTitle').textContent = isLoginMode ? 'Вход в систему' : 'Регистрация';
            this.textContent = isLoginMode ? 'Нет аккаунта? Зарегистрироваться' : 'Уже есть аккаунт? Войти';
            document.getElementById('loginError').textContent = '';
            document.getElementById('registerError').textContent = '';
        });

        // ---------- Вход ----------
        document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('loginError');
            errorDiv.textContent = '';

            try {
                const response = await fetch(`${API_BASE}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Ошибка входа');
                }
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                location.reload();
            } catch (err) {
                errorDiv.textContent = err.message;
            }
        });

        // ---------- Регистрация ----------
        document.getElementById('registerForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('regUsername').value;
            const password = document.getElementById('regPassword').value;
            const password2 = document.getElementById('regPassword2').value;
            const errorDiv = document.getElementById('registerError');
            errorDiv.textContent = '';

            if (password !== password2) {
                errorDiv.textContent = 'Пароли не совпадают';
                return;
            }
            if (password.length < 12) {
                errorDiv.textContent = 'Пароль должен быть не менее 12 символов';
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Ошибка регистрации');
                }
                alert('Пользователь создан! Теперь войдите.');
                document.getElementById('toggleRegisterLink').click();
                document.getElementById('username').value = username;
                document.getElementById('password').value = '';
            } catch (err) {
                errorDiv.textContent = err.message;
            }
        });

        // ---------- Общие функции ----------
        function showLoginPage() {
            document.getElementById('loginPage').style.display = 'block';
            document.getElementById('mainApp').style.display = 'none';
        }

        function showMainApp() {
            document.getElementById('loginPage').style.display = 'none';
            document.getElementById('mainApp').style.display = 'block';
            document.getElementById('globalPingButton')?.classList.toggle(
                'd-none',
                !hasRole('admin', 'operator')
            );
        }

        function logout() {
            localStorage.removeItem('access_token');
            location.reload();
        }

        async function apiFetch(endpoint, options = {}) {
            const token = localStorage.getItem('access_token');
            const headers = { ...options.headers };
            if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const response = await fetch(`${API_BASE}${endpoint}`, {
                ...options,
                headers
            });
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                showLoginPage();
            }
            return response;
        }

        async function apiError(response, fallback = 'Ошибка запроса') {
            try {
                const payload = await response.json();
                if (Array.isArray(payload.detail)) return payload.detail.map(item => item.msg).join('; ');
                return payload.detail || payload.message || fallback;
            } catch (_) {
                return `${fallback} (HTTP ${response.status})`;
            }
        }

        function hasRole(...roles) {
            return Boolean(currentUser && roles.includes(currentUser.role));
        }

        function formatDateTime(value) {
            if (!value) return '—';
            const date = new Date(value);
            return Number.isNaN(date.getTime()) ? escapeHtml(value) : new Intl.DateTimeFormat('ru-RU', {
                dateStyle: 'short', timeStyle: 'medium'
            }).format(date);
        }

        function statusBadge(status) {
            const normalized = String(status || 'unknown').toLowerCase();
            const css = normalized === 'online' || normalized === 'up' ? 'online' : normalized === 'offline' || normalized === 'down' ? 'offline' : 'unknown';
            const label = normalized === 'online' ? 'Online' : normalized === 'offline' ? 'Offline' : normalized === 'up' ? 'Up' : normalized === 'down' ? 'Down' : 'Неизвестно';
            return `<span class="status-badge status-${css}">${label}</span>`;
        }

        function setPageMeta(page, title, subtitle) {
            const meta = PAGE_META[page] || [title || 'Раздел', subtitle || ''];
            document.getElementById('pagePath').textContent = title || meta[0];
            document.getElementById('pageTitle').textContent = title || meta[0];
            document.getElementById('pageSubtitle').textContent = subtitle || meta[1];
        }

        function setActiveNavigation(page) {
            document.querySelectorAll('.nav-link[data-page]').forEach(link => {
                const active = link.dataset.page === page;
                link.classList.toggle('active', active);
                if (active) link.setAttribute('aria-current', 'page');
                else link.removeAttribute('aria-current');
            });
        }

        function showToast(message, type = 'info') {
            const container = document.getElementById('toastContainer');
            if (!container || typeof bootstrap === 'undefined') return;
            const id = `toast-${Date.now()}`;
            const node = document.createElement('div');
            node.id = id;
            node.className = 'toast';
            node.setAttribute('role', 'status');
            node.innerHTML = `<div class="toast-header"><strong class="me-auto">SNMP Monitor</strong><button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Закрыть"></button></div><div class="toast-body ${type === 'danger' ? 'text-danger' : ''}">${escapeHtml(message)}</div>`;
            container.appendChild(node);
            const toast = new bootstrap.Toast(node, { delay: 3500 });
            node.addEventListener('hidden.bs.toast', () => node.remove());
            toast.show();
        }

        // ---------- Навигация (SPA) ----------
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.dataset.page;
                if (page) {
                    loadPage(page);
                }
            });
        });

        // Один обработчик для статических и динамически создаваемых кнопок.
        document.addEventListener('click', (event) => {
            const trigger = event.target.closest('[data-action]');
            if (!trigger) return;

            const action = trigger.dataset.action;
            switch (action) {
                case 'logout': logout(); break;
                case 'open-ping': openPingModal(trigger.dataset.ip || ''); break;
                case 'refresh-devices': refreshDevices(); break;
                case 'load-page': loadPage(trigger.dataset.pageTarget); break;
                case 'download-export': downloadExport(trigger.dataset.resource); break;
                case 'set-user-status': setUserStatus(Number(trigger.dataset.userId), trigger.dataset.active === 'true'); break;
                case 'edit-user': openUserEditor(Number(trigger.dataset.userId)); break;
                case 'view-device': viewDevice(Number(trigger.dataset.deviceId)); break;
                case 'edit-device': editDevice(Number(trigger.dataset.deviceId)); break;
                case 'delete-device': deleteDevice(Number(trigger.dataset.deviceId)); break;
                case 'refresh-port-view': refreshPortView(Number(trigger.dataset.deviceId)); break;
                case 'edit-port': editPort(Number(trigger.dataset.port)); break;
                case 'open-lab-profile': openLabProfile(trigger.dataset.profileId); break;
                default: break;
            }
        });

        document.addEventListener('change', (event) => {
            const control = event.target.closest('[data-action="set-user-role"]');
            if (control) setUserRole(Number(control.dataset.userId), control.value);
        });

        function loadPage(page) {
            currentPage = page;
            setActiveNavigation(page);
            setPageMeta(page);
            const content = document.getElementById('pageContent');
            switch(page) {
                case 'dashboard': renderDashboard(content); break;
                case 'devices': renderDevices(content); break;
                case 'clients': renderClients(content); break;
                case 'printers': renderPrinters(content); break;
                case 'settings': renderSettings(content); break;
                case 'operations': renderOperations(content); break;
                default: content.innerHTML = '<p>Страница не найдена</p>';
            }
            if (window.innerWidth < 992) {
                const menu = document.getElementById('navbarNav');
                if (menu?.classList.contains('show') && typeof bootstrap !== 'undefined') bootstrap.Collapse.getOrCreateInstance(menu).hide();
            }
        }

        // ---------- Рендеринг страниц ----------
        function renderDashboard(container) {
            container.innerHTML = `
                <div class="row mb-3" id="statsCards">
                    <div class="col-xl col-md-4 col-6 mb-2"><div class="card stat-card"><div class="number" id="statTotal">—</div><div class="label">Управляемых устройств</div></div></div>
                    <div class="col-xl col-md-4 col-6 mb-2"><div class="card stat-card online"><div class="number text-success" id="statOnline">—</div><div class="label">Устройств Online</div></div></div>
                    <div class="col-xl col-md-4 col-6 mb-2"><div class="card stat-card offline"><div class="number text-danger" id="statOffline">—</div><div class="label">Устройств Offline</div></div></div>
                    <div class="col-xl col-md-6 col-6 mb-2"><div class="card stat-card"><div class="number" id="statClients">—</div><div class="label">Клиентов в базе</div></div></div>
                    <div class="col-xl col-md-6 col-6 mb-2"><div class="card stat-card online"><div class="number text-success" id="statActiveClients">—</div><div class="label">Активных клиентов</div></div></div>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">График доступности</div>
                            <div class="card-body">
                                <div id="availabilityChartWrap"><canvas id="availabilityChart" height="150"></canvas></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">Последние события</div>
                            <div class="card-body" id="eventsList" style="max-height: 250px; overflow-y: auto;">
                                <p class="text-muted">Загрузка...</p>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            loadStats();
            loadEvents();
            loadAvailabilityChart();
        }

        function renderDevices(container) {
            container.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Список устройств</span>
                        <button class="btn btn-primary btn-sm" type="button" data-action="refresh-devices"><i class="fas fa-sync-alt"></i> Обновить</button>
                    </div>
                    <div class="card-body">
                        <table id="devicesTable" class="table table-bordered table-hover" style="width:100%">
                            <thead>
                                <tr><th>IP</th><th>Имя</th><th>Модель</th><th>Тип</th><th>Статус</th><th>Последний опрос</th><th>Действия</th></tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>
            `;
            if (devicesTable) {
                devicesTable.destroy();
                devicesTable = null;
            }
            loadDevices();
        }

        function renderClients(container) {
            container.innerHTML = `
                <div class="notice"><strong>Как это работает.</strong> Сервер проверяет узлы ICMP и дополняет их данными ARP. Телефоны и Smart TV, блокирующие ping, надёжнее видны через LAN-агент.</div>
                <div class="card">
                    <div class="card-header d-flex flex-wrap gap-2 justify-content-between align-items-center">
                        <span>Таблица клиентов</span>
                        <form id="clientScanForm" class="d-flex flex-wrap gap-2">
                            <input id="clientNetwork" class="form-control form-control-sm" style="width:165px" placeholder="10.20.30.0/24" aria-label="Согласованная сеть CIDR" spellcheck="false" required>
                            <button class="btn btn-primary btn-sm" id="clientScanBtn" type="submit"><i class="fas fa-search me-1"></i>Сканировать</button>
                        </form>
                    </div>
                    <div class="card-body">
                        <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
                            <div id="clientsStatus" class="text-muted" role="status" aria-live="polite">Загрузка…</div>
                            <input id="clientFilter" class="form-control form-control-sm" style="width:220px" placeholder="Поиск IP, MAC или имени" aria-label="Поиск клиента">
                        </div>
                        <div class="table-responsive"><table class="table table-hover"><thead><tr><th>IP</th><th>MAC</th><th>Имя</th><th>Производитель / интерфейс</th><th>Статус</th><th>Последний раз</th><th></th></tr></thead><tbody id="clientsTable"></tbody></table></div>
                    </div>
                </div>`;
            document.getElementById('clientScanForm').addEventListener('submit', event => { event.preventDefault(); scanClients(); });
            document.getElementById('clientFilter').addEventListener('input', renderClientRows);
            loadClients();
        }

        async function loadClients(message = '') {
            const status = document.getElementById('clientsStatus');
            try {
                const res = await apiFetch('/clients');
                if (!res.ok) throw new Error(await apiError(res, 'Не удалось загрузить клиентов'));
                const data = await res.json();
                clientItems = data.items || [];
                renderClientRows();
                status.className = 'text-muted';
                status.textContent = message || `Записей: ${clientItems.length}. Online: ${clientItems.filter(item => item.status === 'online').length}.`;
            } catch (error) {
                status.className = 'text-danger';
                status.textContent = `Ошибка: ${error.message}`;
            }
        }

        function renderClientRows() {
            const body = document.getElementById('clientsTable');
            if (!body) return;
            const query = document.getElementById('clientFilter')?.value.trim().toLowerCase() || '';
            const items = clientItems.filter(client => [client.ip, client.mac, client.hostname, client.vendor, client.status]
                .some(value => String(value || '').toLowerCase().includes(query)));
            body.innerHTML = items.map(client => `<tr>
                <td><code>${escapeHtml(client.ip)}</code></td>
                <td>${escapeHtml(client.mac || '—')}</td>
                <td>${escapeHtml(client.hostname || '—')}</td>
                <td>${escapeHtml(client.vendor || '—')}</td>
                <td>${statusBadge(client.status)}</td>
                <td>${formatDateTime(client.last_seen)}</td>
                <td>${hasRole('admin', 'operator') ? `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="open-ping" data-ip="${escapeHtml(client.ip)}" title="Ping ${escapeHtml(client.ip)}"><i class="fas fa-wave-square"></i></button>` : '—'}</td>
            </tr>`).join('') || '<tr><td colspan="7" class="empty-state"><i class="fas fa-laptop"></i>Клиенты не найдены. Запустите сканирование или LAN-агент.</td></tr>';
        }

        async function scanClients() {
            const status = document.getElementById('clientsStatus');
            const button = document.getElementById('clientScanBtn');
            const network = document.getElementById('clientNetwork').value.trim();
            if (!network.includes('/')) {
                status.className = 'text-danger';
                status.textContent = 'Укажите согласованную сеть в формате CIDR, например 10.20.30.0/24.';
                return;
            }
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Сканирование';
            status.className = 'text-muted';
            status.textContent = 'Идёт ICMP/ARP-сканирование. Сеть /24 может занять до минуты…';
            try {
                const res = await apiFetch('/clients/scan', { method: 'POST', body: JSON.stringify({ network }) });
                if (!res.ok) throw new Error(await apiError(res, 'Ошибка сканирования'));
                const data = await res.json();
                await loadClients(`Сканирование завершено. Ответили: ${data.found ?? (data.items || []).length}. Всего записей: ${clientItems.length}.`);
            } catch (error) {
                status.className = 'text-danger';
                status.textContent = `Ошибка сканирования: ${error.message}`;
            } finally {
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-search me-1"></i>Сканировать';
            }
        }

        function renderPrinters(container) {
            container.innerHTML = `
                <div class="card">
                    <div class="card-header">Принтеры и уровень тонера</div>
                    <div class="card-body">
                        <table id="printersTable" class="table table-bordered" style="width:100%">
                            <thead><tr><th>Имя</th><th>IP</th><th>Модель</th><th>Тонер (%)</th><th>Статус</th><th>Ошибка</th></tr></thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>
            `;
            if (printersTable) {
                printersTable.destroy();
                printersTable = null;
            }
            loadPrinters();
        }

        function renderSettings(container) {
            const canManageDevices = hasRole('admin', 'operator');
            container.innerHTML = `
                ${canManageDevices ? `<div class="card">
                    <div class="card-header">SNMP-обнаружение управляемого оборудования</div>
                    <div class="card-body">
                        <div class="notice">Этот поиск добавляет только узлы, которые отвечают и на ICMP, и на SNMP. Для обычных телефонов и ТВ используйте раздел «Клиенты сети».</div>
                        <form id="discoveryForm">
                            <div class="row g-2">
                                <div class="col-md-4">
                                    <label for="networkInput" class="form-label">Сеть (CIDR)</label>
                                    <input type="text" class="form-control" id="networkInput" placeholder="10.20.30.0/24" spellcheck="false" required>
                                </div>
                                <div class="col-md-3">
                                    <label for="communityInput" class="form-label">SNMP Community</label>
                                    <input type="password" class="form-control" id="communityInput" placeholder="read-only community" autocomplete="off" required>
                                </div>
                                <div class="col-md-3">
                                    <label for="snmpVersionSelect" class="form-label">Версия SNMP</label>
                                    <select class="form-select" id="snmpVersionSelect">
                                        <option value="v2c">v2c</option>
                                        <option value="v1">v1</option>
                                    </select>
                                </div>
                                <div class="col-md-2 d-flex align-items-end">
                                    <button type="submit" class="btn btn-primary w-100" id="discoveryBtn">
                                        <i class="fas fa-search"></i> Сканировать
                                    </button>
                                </div>
                            </div>
                        </form>
                        <div id="discoveryResult" class="mt-3"></div>
                    </div>
                </div>
                <div class="card mt-3">
                    <div class="card-header">Добавить устройство вручную</div>
                    <div class="card-body">
                        <form id="addDeviceForm" class="row g-2">
                            <div class="col-md-3"><label class="form-label" for="deviceIp">IP-адрес</label><input id="deviceIp" class="form-control" placeholder="10.20.30.10" required></div>
                            <div class="col-md-3"><label class="form-label" for="deviceHostname">Имя</label><input id="deviceHostname" class="form-control" placeholder="Access-SW-01"></div>
                            <div class="col-md-2"><label class="form-label" for="deviceType">Тип</label><select id="deviceType" class="form-select"><option value="switch">Коммутатор</option><option value="router">Маршрутизатор</option><option value="printer">Принтер</option></select></div>
                            <div class="col-md-2"><label class="form-label" for="deviceVersion">SNMP</label><select id="deviceVersion" class="form-select"><option value="v3">v3 (SHA/AES)</option><option value="v2c">v2c</option><option value="v1">v1</option></select></div>
                            <div class="col-md-2" id="deviceCommunityGroup"><label class="form-label" for="deviceCommunity">Community</label><input id="deviceCommunity" type="password" autocomplete="off" class="form-control" placeholder="read-only community"></div>
                            <div class="col-12" id="deviceV3Fields">
                                <div class="row g-2">
                                    <div class="col-md-4"><label class="form-label" for="deviceSnmpUser">SNMPv3 User</label><input id="deviceSnmpUser" autocomplete="off" class="form-control"></div>
                                    <div class="col-md-4"><label class="form-label" for="deviceSnmpAuth">Auth password (SHA)</label><input id="deviceSnmpAuth" type="password" autocomplete="new-password" class="form-control"></div>
                                    <div class="col-md-4"><label class="form-label" for="deviceSnmpPriv">Privacy password (AES)</label><input id="deviceSnmpPriv" type="password" autocomplete="new-password" class="form-control"></div>
                                </div>
                            </div>
                            <div class="col-md-8"><label class="form-label" for="deviceModel">Модель (необязательно)</label><input id="deviceModel" class="form-control" placeholder="Например, MikroTik hAP ax3"></div>
                            <div class="col-md-4 d-flex align-items-end"><button id="addDeviceBtn" class="btn btn-primary w-100" type="submit">Добавить устройство</button></div>
                        </form>
                        <div id="addDeviceResult" class="mt-3"></div>
                    </div>
                </div>` : `<div class="notice"><strong>Режим просмотра.</strong> Роль ${escapeHtml(currentUser?.role || 'viewer')} не может добавлять управляемые устройства.</div>`}
                <div class="card mt-3" id="labProfilesCard">
                    <div class="card-header">Лаборатория без оборудования</div>
                    <div class="card-body">
                        <p class="text-muted">Профили позволяют проверять экраны VLAN, FDB, ARP, PoE и расходных материалов без SNMP-запросов.</p>
                        <div id="labProfiles" class="lab-profile-grid"><span class="text-muted">Загрузка профилей…</span></div>
                    </div>
                </div>
            `;

            document.getElementById('discoveryForm')?.addEventListener('submit', async (e) => {
                e.preventDefault();
                await runDiscovery();
            });
            document.getElementById('addDeviceForm')?.addEventListener('submit', async (e) => {
                e.preventDefault();
                await addDevice();
            });
            const versionSelect = document.getElementById('deviceVersion');
            const updateCredentialFields = () => {
                const isV3 = versionSelect?.value === 'v3';
                document.getElementById('deviceCommunityGroup')?.classList.toggle('d-none', isV3);
                document.getElementById('deviceV3Fields')?.classList.toggle('d-none', !isV3);
            };
            versionSelect?.addEventListener('change', updateCredentialFields);
            updateCredentialFields();
            loadLabProfiles();
        }

        function renderOperations(container) {
            const isAdmin = hasRole('admin');
            const disabled = isAdmin ? '' : 'disabled';
            container.innerHTML = `<div class="row g-3">
                <div class="col-lg-5">
                    <div class="card"><div class="card-header">Параметры мониторинга</div><div class="card-body">
                        ${isAdmin ? '' : '<div class="notice">Параметры показаны без права изменения.</div>'}
                        <form id="opsSettingsForm"><label class="form-label" for="pollInterval">Интервал опроса, с</label><input id="pollInterval" class="form-control mb-2" type="number" min="15" max="3600" ${disabled}><label class="form-label" for="pingCount">Ping: число пакетов</label><input id="pingCount" class="form-control mb-2" type="number" min="1" max="10" ${disabled}><label class="form-label" for="pingTimeout">Ping timeout, с</label><input id="pingTimeout" class="form-control mb-3" type="number" min="1" max="10" ${disabled}>${isAdmin ? '<button class="btn btn-primary" id="opsSaveBtn" type="submit"><i class="fas fa-save me-1"></i>Сохранить</button>' : ''}</form><div id="opsResult" class="mt-2" role="status"></div>
                    </div></div>
                    <div class="card mt-3"><div class="card-header">Экспорт CSV</div><div class="card-body d-flex flex-wrap gap-2"><button class="btn btn-outline-secondary btn-sm" type="button" data-action="download-export" data-resource="devices">Устройства</button><button class="btn btn-outline-secondary btn-sm" type="button" data-action="download-export" data-resource="events">События</button><button class="btn btn-outline-secondary btn-sm" type="button" data-action="download-export" data-resource="clients">Клиенты</button><button class="btn btn-outline-secondary btn-sm" type="button" data-action="download-export" data-resource="availability">Доступность</button></div></div>
                </div>
                <div class="col-lg-7">${isAdmin ? `<div class="card"><div class="card-header">Аудит действий</div><div class="card-body"><div id="auditList" class="small text-muted">Загрузка…</div></div></div><div class="card mt-3"><div class="card-header">Пользователи и роли</div><div class="card-body"><form id="createUserForm" class="row g-2 mb-3"><div class="col-md-3"><input id="newUsername" class="form-control form-control-sm" placeholder="Логин" minlength="3" required></div><div class="col-md-3"><input id="newUserEmail" type="email" class="form-control form-control-sm" placeholder="Email"></div><div class="col-md-3"><input id="newUserPassword" type="password" class="form-control form-control-sm" placeholder="Пароль (12+)" minlength="12" required></div><div class="col-md-2"><select id="newUserRole" class="form-select form-select-sm"><option value="viewer">viewer</option><option value="operator">operator</option><option value="admin">admin</option></select></div><div class="col-md-1"><button class="btn btn-primary btn-sm" title="Создать"><i class="fas fa-plus"></i></button></div></form><div id="usersList" class="small text-muted">Загрузка…</div></div></div>` : `<div class="card"><div class="card-header">Права доступа</div><div class="card-body"><p>Ваша роль: <strong>${escapeHtml(currentUser?.role || 'viewer')}</strong>.</p><p class="text-muted mb-0">Аудит, изменение параметров и ролей доступны администратору. Запрещённые API-запросы не отправляются.</p></div></div>`}</div>
            </div>`;
            loadOperations();
            if (isAdmin) document.getElementById('opsSettingsForm').addEventListener('submit', saveOperations);
            if (isAdmin) document.getElementById('createUserForm').addEventListener('submit', createUser);
        }

        async function loadOperations() {
            try {
                const settingsRes = await apiFetch('/operations/settings');
                if (!settingsRes.ok) throw new Error(await apiError(settingsRes, 'Не удалось получить настройки'));
                const settings = await settingsRes.json();
                document.getElementById('pollInterval').value = settings.poll_interval_seconds;
                document.getElementById('pingCount').value = settings.ping_count;
                document.getElementById('pingTimeout').value = settings.ping_timeout_seconds;
                pingDefaults = { count: settings.ping_count, timeout: settings.ping_timeout_seconds };
                if (!hasRole('admin')) return;
                const [auditRes, usersRes] = await Promise.all([apiFetch('/operations/audit'), apiFetch('/admin/users')]);
                if (!auditRes.ok) throw new Error(await apiError(auditRes, 'Не удалось загрузить аудит'));
                const audit = await auditRes.json();
                document.getElementById('auditList').innerHTML = audit.length ? audit.map(item => `<div class="event-row"><div><strong>${escapeHtml(item.action)}</strong> · ${escapeHtml(item.username)}<br><span class="text-muted">${escapeHtml(item.details || '—')}</span></div><span class="event-time">${formatDateTime(item.time)}</span></div>`).join('') : 'Записей пока нет';
                if (!usersRes.ok) throw new Error(await apiError(usersRes, 'Не удалось загрузить пользователей'));
                const users = await usersRes.json();
                managedUsers = users;
                document.getElementById('usersList').innerHTML = users.map(user => `<div class="d-flex flex-wrap gap-2 align-items-center border-bottom py-2"><span class="flex-grow-1"><strong>${escapeHtml(user.username)}</strong>${user.id === currentUser.id ? ' <span class="text-muted">(вы)</span>' : ''}<br><span class="text-muted">${escapeHtml(user.email || 'email не задан')} · ${user.is_active ? 'активен' : 'заблокирован'}</span></span><select class="form-select form-select-sm" style="max-width:125px" data-action="set-user-role" data-user-id="${Number(user.id)}" ${user.id === currentUser.id ? 'disabled' : ''}><option value="admin" ${user.role==='admin'?'selected':''}>admin</option><option value="operator" ${user.role==='operator'?'selected':''}>operator</option><option value="viewer" ${user.role==='viewer'?'selected':''}>viewer</option></select>${user.id === currentUser.id ? '' : `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="set-user-status" data-user-id="${Number(user.id)}" data-active="${!user.is_active}">${user.is_active ? 'Блокировать' : 'Включить'}</button><button class="btn btn-outline-secondary btn-sm" type="button" data-action="edit-user" data-user-id="${Number(user.id)}" title="Редактировать"><i class="fas fa-pen"></i></button>`}</div>`).join('') || 'Пользователей нет';
            } catch (error) {
                const target = document.getElementById('auditList') || document.getElementById('opsResult');
                if (target) { target.className = 'text-danger'; target.textContent = `Ошибка: ${error.message}`; }
            }
        }

        async function saveOperations(event) {
            event.preventDefault();
            if (!hasRole('admin')) return;
            const data = {poll_interval_seconds: Number(document.getElementById('pollInterval').value), ping_count: Number(document.getElementById('pingCount').value), ping_timeout_seconds: Number(document.getElementById('pingTimeout').value)};
            const result = document.getElementById('opsResult');
            const button = document.getElementById('opsSaveBtn');
            button.disabled = true;
            try {
                const res = await apiFetch('/operations/settings', {method: 'PUT', body: JSON.stringify(data)});
                if (!res.ok) throw new Error(await apiError(res, 'Ошибка сохранения'));
                pingDefaults = { count: data.ping_count, timeout: data.ping_timeout_seconds };
                result.className = 'text-success mt-2';
                result.textContent = 'Параметры сохранены.';
            } catch (error) {
                result.className = 'text-danger mt-2';
                result.textContent = error.message;
            } finally { button.disabled = false; }
        }

        async function setUserRole(userId, role) {
            const res = await apiFetch(`/admin/users/${userId}/role`, {method:'PUT', body:JSON.stringify({role})});
            if (!res.ok) {
                showToast(await apiError(res, 'Роль не изменена'), 'danger');
                await loadOperations();
                return;
            }
            showToast('Роль пользователя обновлена');
            await loadOperations();
        }

        async function createUser(event) {
            event.preventDefault();
            const email = document.getElementById('newUserEmail').value.trim();
            const payload = {
                username: document.getElementById('newUsername').value.trim(),
                email: email || null,
                password: document.getElementById('newUserPassword').value,
                role: document.getElementById('newUserRole').value
            };
            const response = await apiFetch('/admin/users', { method: 'POST', body: JSON.stringify(payload) });
            if (!response.ok) return showToast(await apiError(response, 'Пользователь не создан'), 'danger');
            event.target.reset();
            showToast('Пользователь создан');
            await loadOperations();
        }

        function openUserEditor(userId) {
            if (!hasRole('admin')) return;
            const user = managedUsers.find(item => Number(item.id) === Number(userId));
            if (!user) {
                showToast('Пользователь не найден. Обновите список.', 'danger');
                return;
            }
            if (Number(user.id) === Number(currentUser?.id)) {
                showToast('Свою учётную запись нельзя менять через панель администрирования.', 'danger');
                return;
            }

            document.getElementById('editUserId').value = user.id;
            document.getElementById('editUsername').value = user.username;
            document.getElementById('editUserEmail').value = user.email || '';
            document.getElementById('editUserPassword').value = '';
            document.getElementById('editUserRole').value = user.role;
            document.getElementById('editUserActive').value = String(Boolean(user.is_active));
            document.getElementById('userEditModalTitle').textContent = `Редактирование: ${user.username}`;
            const result = document.getElementById('userEditResult');
            result.className = 'mt-3';
            result.textContent = '';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('userEditModal')).show();
        }

        async function saveUserChanges(event) {
            event.preventDefault();
            if (!hasRole('admin')) return;

            const userId = Number(document.getElementById('editUserId').value);
            const result = document.getElementById('userEditResult');
            const button = document.getElementById('userEditSave');
            if (!userId || userId === Number(currentUser?.id)) {
                result.className = 'text-danger mt-3';
                result.textContent = 'Эту учётную запись нельзя изменить из панели администрирования.';
                return;
            }

            const original = managedUsers.find(item => Number(item.id) === userId);
            if (!original) {
                result.className = 'text-danger mt-3';
                result.textContent = 'Пользователь не найден. Закройте окно и обновите список.';
                return;
            }

            const username = document.getElementById('editUsername').value.trim();
            const email = document.getElementById('editUserEmail').value.trim() || null;
            const password = document.getElementById('editUserPassword').value;
            const role = document.getElementById('editUserRole').value;
            const isActive = document.getElementById('editUserActive').value === 'true';
            const payload = {};
            if (username !== original.username) payload.username = username;
            if (email !== (original.email || null)) payload.email = email;
            if (role !== original.role) payload.role = role;
            if (isActive !== Boolean(original.is_active)) payload.is_active = isActive;
            if (password) payload.password = password;

            if (!Object.keys(payload).length) {
                result.className = 'text-muted mt-3';
                result.textContent = 'Изменений нет.';
                return;
            }

            button.disabled = true;
            result.className = 'text-muted mt-3';
            result.textContent = 'Сохранение…';
            try {
                const response = await apiFetch(`/admin/users/${userId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(payload)
                });
                if (!response.ok) throw new Error(await apiError(response, 'Пользователь не обновлён'));
                bootstrap.Modal.getOrCreateInstance(document.getElementById('userEditModal')).hide();
                showToast('Учётная запись обновлена');
                await loadOperations();
            } catch (error) {
                result.className = 'text-danger mt-3';
                result.textContent = error.message;
            } finally {
                button.disabled = false;
            }
        }

        async function setUserStatus(userId, isActive) {
            const response = await apiFetch(`/admin/users/${userId}/status`, { method: 'PUT', body: JSON.stringify({ is_active: isActive }) });
            if (!response.ok) return showToast(await apiError(response, 'Статус не изменён'), 'danger');
            showToast('Статус пользователя обновлён');
            await loadOperations();
        }

        async function downloadExport(resource) {
            const res = await apiFetch(`/operations/export/${resource}`);
            if (!res.ok) return showToast(await apiError(res, 'Экспорт пока недоступен'), 'danger');
            const url = URL.createObjectURL(await res.blob());
            const link = document.createElement('a');
            const disposition = res.headers.get('Content-Disposition') || '';
            link.href = url;
            link.download = disposition.match(/filename="?([^";]+)"?/)?.[1] || `${resource}.csv`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }

        async function addDevice() {
            const result = document.getElementById('addDeviceResult');
            const button = document.getElementById('addDeviceBtn');
            button.disabled = true;
            result.textContent = 'Добавление устройства…';
            const device = {
                ip: document.getElementById('deviceIp').value.trim(),
                hostname: document.getElementById('deviceHostname').value.trim(),
                model: document.getElementById('deviceModel').value.trim(),
                device_type: document.getElementById('deviceType').value,
                snmp_version: document.getElementById('deviceVersion').value,
                community: document.getElementById('deviceCommunity').value.trim() || null,
                snmp_user: document.getElementById('deviceSnmpUser').value.trim() || null,
                snmp_auth: document.getElementById('deviceSnmpAuth').value || null,
                snmp_priv: document.getElementById('deviceSnmpPriv').value || null
            };
            try {
                const res = await apiFetch('/admin/devices', { method: 'POST', body: JSON.stringify(device) });
                if (!res.ok) throw new Error((await res.json()).detail || 'Не удалось добавить устройство');
                result.className = 'mt-3 text-success';
                result.textContent = 'Устройство добавлено. Теперь можно открыть его порты в списке устройств.';
                document.getElementById('addDeviceForm').reset();
                document.getElementById('deviceVersion')?.dispatchEvent(new Event('change'));
            } catch (error) {
                result.className = 'mt-3 text-danger';
                result.textContent = `Ошибка: ${error.message}`;
            } finally {
                button.disabled = false;
            }
        }

        // ---------- Обнаружение устройств ----------
        async function runDiscovery() {
            const network = document.getElementById('networkInput').value.trim();
            const community = document.getElementById('communityInput').value.trim();
            const snmp_version = document.getElementById('snmpVersionSelect').value;
            const resultDiv = document.getElementById('discoveryResult');
            const btn = document.getElementById('discoveryBtn');

            if (!network || !community) {
                resultDiv.innerHTML = `<div class="alert alert-danger">Укажите сеть CIDR и read-only community</div>`;
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Сканирование...';
            resultDiv.innerHTML = '<div class="alert alert-info">Идёт сканирование, это может занять несколько минут...</div>';

            try {
                const res = await apiFetch('/discovery/scan', {
                    method: 'POST',
                    body: JSON.stringify({ network, community, snmp_version })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Ошибка сканирования');
                }

                const data = await res.json();
                let html = `<div class="alert alert-success">`;
                html += `<strong>Найдено устройств:</strong> ${data.discovered || 0}<br>`;
                html += `<strong>Добавлено в БД:</strong> ${data.added || 0}<br>`;
                if (data.devices && data.devices.length) {
            html += `<strong>Добавленные IP:</strong> ${data.devices.map(device => device.ip).join(', ')}`;
                } else {
                    html += `<span class="text-muted">Нет новых устройств</span>`;
                }
                html += `</div>`;
                resultDiv.innerHTML = html;

                if (currentPage === 'devices') {
                    loadDevices();
                } else {
                    document.querySelector('[data-page="devices"]').click();
                }
            } catch (err) {
                resultDiv.innerHTML = `<div class="alert alert-danger">Ошибка: ${err.message}</div>`;
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-search"></i> Сканировать';
            }
        }

        // ---------- Загрузка данных (только реальные запросы) ----------
        async function loadStats() {
            try {
                const res = await apiFetch('/dashboard/stats');
                if (!res.ok) throw new Error('Ошибка получения статистики');
                const data = await res.json();
                document.getElementById('statTotal').textContent = data.total ?? 0;
                document.getElementById('statOnline').textContent = data.online ?? 0;
                document.getElementById('statOffline').textContent = data.offline ?? 0;
                document.getElementById('statClients').textContent = data.clients ?? 0;
                document.getElementById('statActiveClients').textContent = data.active_clients ?? 0;
            } catch (err) {
                console.error('loadStats error:', err);
                ['statTotal', 'statOnline', 'statOffline', 'statClients', 'statActiveClients'].forEach(id => {
                    const node = document.getElementById(id);
                    if (node) node.textContent = '—';
                });
            }
        }

        async function loadAvailabilityChart() {
            try {
                const res = await apiFetch('/devices');
                if (!res.ok) throw new Error(await apiError(res, 'Ошибка загрузки доступности'));
                const data = await res.json();
                const items = data.items || [];
                initChart(items.filter(item => item.status === 'online').length, items.filter(item => item.status !== 'online').length);
            } catch (error) {
                const wrap = document.getElementById('availabilityChartWrap');
                if (wrap) wrap.innerHTML = `<div class="empty-state">График недоступен: ${escapeHtml(error.message)}</div>`;
            }
        }

        async function loadEvents() {
            const list = document.getElementById('eventsList');
            if (!list) return;
            try {
                const res = await apiFetch('/dashboard/events');
                if (!res.ok) throw new Error('Ошибка загрузки событий');
                const events = await res.json();
                if (!events || events.length === 0) {
                    list.innerHTML = '<p class="text-muted">Нет событий</p>';
                    return;
                }
                list.innerHTML = events.map(e => `
                    <div class="event-row">
                        <span>${escapeHtml(e.msg || '—')}</span>
                        <span class="event-time">${formatDateTime(e.time)}</span>
                    </div>
                `).join('');
            } catch (err) {
                console.error('loadEvents error:', err);
                list.innerHTML = '<p class="text-muted">Ошибка загрузки событий</p>';
            }
        }

        async function loadDevices() {
            try {
                const res = await apiFetch('/devices');
                if (!res.ok) throw new Error('Ошибка загрузки устройств');
                const data = await res.json();
                const items = data.items || [];
                cachedDevices = new Map(items.map(device => [Number(device.id), device]));
                // Считаем online/offline для графика
                const online = items.filter(d => d.status === 'online').length;
                const offline = items.filter(d => d.status === 'offline').length;
                if (document.getElementById('availabilityChart')) {
                    initChart(online, offline);
                }
                renderDevicesTable(items);
            } catch (err) {
                console.error('loadDevices error:', err);
                const tbody = document.querySelector('#devicesTable tbody');
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Ошибка загрузки устройств</td></tr>`;
                }
            }
        }

        function renderDevicesTable(items) {
            const tbody = document.querySelector('#devicesTable tbody');
            if (!tbody) return;
            if (!items || items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="fas fa-server"></i>Управляемые устройства пока не добавлены</td></tr>`;
                return;
            }
            tbody.innerHTML = items.map(d => `
                <tr>
                    <td><code>${escapeHtml(d.ip)}</code></td>
                    <td>${escapeHtml(d.hostname || '—')}</td>
                    <td>${escapeHtml(d.model || '—')}</td>
                    <td>${escapeHtml(d.type || '—')}</td>
                    <td>${statusBadge(d.status)}</td>
                    <td>${formatDateTime(d.last_seen)}</td>
                    <td>
                        ${hasRole('admin', 'operator') ? `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="open-ping" data-ip="${escapeHtml(d.ip)}"><i class="fas fa-wave-square"></i> Ping</button>` : ''}
                        ${d.type === 'switch' ? `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="view-device" data-device-id="${Number(d.id)}" title="Открыть порты"><i class="fas fa-ethernet"></i></button>` : ''}
                        ${hasRole('admin', 'operator') ? `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="edit-device" data-device-id="${Number(d.id)}" title="Изменить"><i class="fas fa-pen"></i></button>` : ''}
                        ${hasRole('admin') ? `<button class="btn btn-outline-danger btn-sm" type="button" data-action="delete-device" data-device-id="${Number(d.id)}" title="Удалить"><i class="fas fa-trash"></i></button>` : ''}
                    </td>
                </tr>
            `).join('');
            if (window.jQuery && $.fn.DataTable) {
                if (devicesTable) devicesTable.destroy();
                devicesTable = $('#devicesTable').DataTable({
                    pageLength: 10,
                    ordering: true,
                    searching: true,
                    language: { search: 'Поиск:', lengthMenu: 'Показать _MENU_', info: '_START_–_END_ из _TOTAL_', infoEmpty: 'Нет записей', zeroRecords: 'Совпадений нет', paginate: { previous: 'Назад', next: 'Далее' } }
                });
            }
        }

        async function loadPrinters() {
            try {
                const res = await apiFetch('/printers/');
                if (!res.ok) throw new Error('Ошибка загрузки принтеров');
                const data = await res.json();
                renderPrintersTable(data);
            } catch (err) {
                console.error('loadPrinters error:', err);
                const tbody = document.querySelector('#printersTable tbody');
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Ошибка загрузки принтеров</td></tr>`;
                }
            }
        }

        function renderPrintersTable(items) {
            const tbody = document.querySelector('#printersTable tbody');
            if (!tbody) return;
            if (!items || items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Нет принтеров</td></tr>`;
                return;
            }
            tbody.innerHTML = items.map(p => `
                <tr>
                    <td>${escapeHtml(p.name || '—')}</td>
                    <td><code>${escapeHtml(p.ip)}</code></td>
                    <td>${escapeHtml(p.model || '—')}</td>
                    <td>
                        ${Number.isFinite(Number(p.toner)) ? `<div class="toner-bar"><div class="progress-fill ${Number(p.toner) < 20 ? 'danger' : Number(p.toner) < 50 ? 'warning' : ''}" style="width:${Math.max(0, Math.min(100, Number(p.toner)))}%"></div></div><span class="small">${escapeHtml(p.toner)}%</span>` : '—'}
                    </td>
                    <td>${statusBadge(p.status)}</td>
                    <td>${escapeHtml(p.error || '—')}</td>
                </tr>
            `).join('');
            if (window.jQuery && $.fn.DataTable) {
                if (printersTable) printersTable.destroy();
                printersTable = $('#printersTable').DataTable({
                    pageLength: 10,
                    ordering: true,
                    searching: true,
                    language: { search: 'Поиск:', lengthMenu: 'Показать _MENU_', info: '_START_–_END_ из _TOTAL_', infoEmpty: 'Нет записей', zeroRecords: 'Совпадений нет', paginate: { previous: 'Назад', next: 'Далее' } }
                });
            }
        }

        function initChart(online, offline) {
            const ctx = document.getElementById('availabilityChart');
            if (!ctx) return;
            if (typeof Chart === 'undefined') {
                document.getElementById('availabilityChartWrap').innerHTML = '<div class="empty-state">Библиотека графиков не загружена</div>';
                return;
            }
            if (window._chartInstance) {
                window._chartInstance.destroy();
            }
            window._chartInstance = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Online', 'Offline'],
                    datasets: [{
                        data: [online || 0, offline || 0],
                        backgroundColor: ['#198754', '#dc3545'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'bottom' }
                    }
                }
            });
        }

        // ---------- Действия ----------
        function refreshDevices() {
            loadDevices();
        }

        function openPingModal(ip = '') {
            if (!hasRole('admin', 'operator')) {
                showToast('Ping доступен администратору и оператору', 'danger');
                return;
            }
            document.getElementById('pingIp').value = ip;
            document.getElementById('pingCountModal').value = pingDefaults.count;
            document.getElementById('pingTimeoutModal').value = pingDefaults.timeout;
            document.getElementById('pingResult').innerHTML = '';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('pingModal')).show();
        }

        function pingDevice(ip) {
            openPingModal(ip);
        }

        function viewDevice(id) {
            renderPortView(id);
        }

        async function editDevice(id) {
            const device = cachedDevices.get(Number(id));
            if (!device) return;
            const hostname = prompt('Имя устройства:', device.hostname || '');
            if (hostname === null) return;
            const model = prompt('Модель:', device.model || '');
            if (model === null) return;
            const response = await apiFetch(`/devices/${id}`, { method: 'PATCH', body: JSON.stringify({ hostname, model }) });
            if (!response.ok) return showToast(await apiError(response, 'Не удалось изменить устройство'), 'danger');
            showToast('Устройство обновлено'); loadDevices();
        }

        async function deleteDevice(id) {
            const device = cachedDevices.get(Number(id));
            if (!confirm(`Удалить ${device?.hostname || device?.ip || `устройство ${id}`} и его историю?`)) return;
            const response = await apiFetch(`/devices/${id}`, { method: 'DELETE' });
            if (!response.ok) return showToast(await apiError(response, 'Не удалось удалить устройство'), 'danger');
            showToast('Устройство удалено'); loadDevices();
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>'"]/g, char => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
            })[char]);
        }

        async function renderPortView(deviceId) {
            currentPage = 'ports';
            window.currentPortDeviceId = Number(deviceId);
            const content = document.getElementById('pageContent');
            content.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex flex-wrap gap-2 justify-content-between align-items-center">
                        <span><i class="fas fa-ethernet me-2"></i>Порты коммутатора</span>
                        <div>
                            <button class="btn btn-outline-secondary btn-sm" type="button" data-action="load-page" data-page-target="devices">К устройствам</button>
                            <button id="refreshPortsBtn" class="btn btn-primary btn-sm" type="button" data-action="refresh-port-view" data-device-id="${Number(deviceId)}"><i class="fas fa-sync-alt"></i> Опросить SNMP</button>
                        </div>
                    </div>
                    <div class="card-body">
                        <div id="portsStatus" class="text-muted mb-3">Загрузка сохранённого снимка...</div>
                        <div class="table-responsive">
                            <table class="table table-bordered table-hover align-middle">
                                <thead><tr><th>Порт</th><th>Статус</th><th>Описание</th><th>Режим</th><th>PVID</th><th>Скорость</th><th>MAC</th><th>IP из ARP</th><th></th></tr></thead>
                                <tbody id="portsTableBody"></tbody>
                            </table>
                        </div>
                    </div>
                </div>`;
            await loadPortView(deviceId);
        }

        async function loadPortView(deviceId) {
            const status = document.getElementById('portsStatus');
            const tbody = document.getElementById('portsTableBody');
            try {
                const res = await apiFetch(`/devices/${deviceId}/ports`);
                if (!res.ok) throw new Error((await res.json()).detail || 'Не удалось получить порты');
                renderPorts(await res.json(), tbody);
                status.textContent = 'Показан последний сохранённый снимок. Нажмите «Опросить SNMP» для обновления.';
            } catch (error) {
                status.className = 'text-danger mb-3';
                status.textContent = `Ошибка: ${error.message}`;
            }
        }

        function renderPorts(ports, tbody, allowEdit = true) {
            if (!ports?.length) {
                tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">Портов пока нет. Запустите опрос SNMP.</td></tr>';
                return;
            }
            tbody.innerHTML = ports.map(port => {
                const macs = port.macs || [];
                const ips = port.ips || [];
                return `<tr>
                    <td>${escapeHtml(port.port)}</td>
                    <td><span class="badge bg-${port.status === 'up' ? 'success' : 'secondary'}">${escapeHtml(port.status)}</span></td>
                    <td>${escapeHtml(port.description || '—')}</td>
                    <td>${escapeHtml(port.mode || '—')}</td>
                    <td>${port.pvid ?? '—'}</td>
                    <td>${escapeHtml(port.speed || '—')}</td>
                    <td><span title="${escapeHtml(macs.join(', '))}">${macs.length ? `${macs.length}: ${escapeHtml(macs.slice(0, 2).join(', '))}${macs.length > 2 ? '…' : ''}` : '—'}</span></td>
                    <td>${ips.length ? escapeHtml(ips.join(', ')) : '—'}</td>
                    <td>${allowEdit ? `<button class="btn btn-outline-secondary btn-sm" type="button" data-action="edit-port" data-port="${escapeHtml(port.port)}">Изменить</button>` : '—'}</td>
                </tr>`;
            }).join('');
        }

        async function showLabSwitch() {
            const content = document.getElementById('pageContent');
            content.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center"><span><i class="fas fa-flask me-2"></i>LAB-SW-24G · эмулятор</span><button class="btn btn-outline-secondary btn-sm" type="button" data-action="load-page" data-page-target="settings">К настройкам</button></div>
                    <div class="card-body"><p id="labStatus" class="text-muted">Загрузка тестового профиля…</p><div class="table-responsive"><table class="table table-bordered table-hover align-middle"><thead><tr><th>Порт</th><th>Статус</th><th>Описание</th><th>Режим</th><th>PVID</th><th>Скорость</th><th>MAC</th><th>IP из ARP</th><th></th></tr></thead><tbody id="portsTableBody"></tbody></table></div></div>
                </div>`;
            try {
                const res = await apiFetch('/lab/profiles/access-switch');
                if (!res.ok) throw new Error('Не удалось загрузить demo-профиль');
                const data = await res.json();
                renderPorts(data.ports, document.getElementById('portsTableBody'), false);
                document.getElementById('labStatus').textContent = 'Детерминированные тестовые данные: без SNMP-запросов к сети.';
            } catch (error) {
                document.getElementById('labStatus').className = 'text-danger';
                document.getElementById('labStatus').textContent = `Ошибка: ${error.message}`;
            }
        }

        async function loadLabProfiles() {
            const target = document.getElementById('labProfiles');
            if (!target) return;
            try {
                const response = await apiFetch('/lab/profiles');
                if (response.status === 404) {
                    document.getElementById('labProfilesCard')?.remove();
                    return;
                }
                if (!response.ok) throw new Error(await apiError(response, 'Не удалось загрузить профили'));
                const data = await response.json();
                target.innerHTML = (data.items || []).map(profile => `<button class="lab-profile" type="button" data-action="open-lab-profile" data-profile-id="${escapeHtml(profile.id)}"><i class="fas ${profile.type === 'printer' ? 'fa-print' : profile.type === 'router' ? 'fa-router' : 'fa-network-wired'}"></i><strong>${escapeHtml(profile.name)}</strong><span>${escapeHtml(profile.type)}</span></button>`).join('') || '<span class="text-muted">Профилей нет</span>';
            } catch (error) {
                target.innerHTML = `<span class="text-danger">${escapeHtml(error.message)}</span>`;
            }
        }

        async function openLabProfile(profileId) {
            currentPage = 'lab'; setActiveNavigation('settings'); setPageMeta('lab');
            const content = document.getElementById('pageContent');
            const response = await apiFetch(`/lab/profiles/${encodeURIComponent(profileId)}`);
            if (!response.ok) { content.innerHTML = `<div class="notice">${escapeHtml(await apiError(response))}</div>`; return; }
            const data = await response.json();
            if (Array.isArray(data.ports)) {
                content.innerHTML = `<div class="card"><div class="card-header d-flex justify-content-between"><span>${escapeHtml(data.name)}</span><button class="btn btn-outline-secondary btn-sm" type="button" data-action="load-page" data-page-target="settings">Назад</button></div><div class="card-body"><div class="table-responsive"><table class="table table-bordered"><thead><tr><th>Порт</th><th>Статус</th><th>Описание</th><th>Режим</th><th>PVID</th><th>Скорость</th><th>MAC</th><th>IP</th><th></th></tr></thead><tbody id="portsTableBody"></tbody></table></div></div></div>`;
                renderPorts(data.ports, document.getElementById('portsTableBody'), false);
            } else {
                content.innerHTML = `<div class="card"><div class="card-header d-flex justify-content-between"><span>${escapeHtml(data.name || profileId)}</span><button class="btn btn-outline-secondary btn-sm" type="button" data-action="load-page" data-page-target="settings">Назад</button></div><div class="card-body"><pre class="lab-json">${escapeHtml(JSON.stringify(data, null, 2))}</pre></div></div>`;
            }
        }

        async function refreshPortView(deviceId) {
            const button = document.getElementById('refreshPortsBtn');
            const status = document.getElementById('portsStatus');
            button.disabled = true;
            status.className = 'text-muted mb-3';
            status.textContent = 'Выполняется SNMP-опрос портов, FDB, ARP и PVID…';
            try {
                const res = await apiFetch(`/devices/${deviceId}/ports/refresh`, { method: 'POST' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Ошибка SNMP-опроса');
                const data = await res.json();
                renderPorts(data.items, document.getElementById('portsTableBody'));
                status.textContent = `Опрос завершён: получено портов — ${data.count}.`;
            } catch (error) {
                status.className = 'text-danger mb-3';
                status.textContent = `Ошибка: ${error.message}`;
            } finally {
                button.disabled = false;
            }
        }

        async function editPort(portNumber) {
            const description = prompt('Описание порта (локальная метка):');
            if (description === null) return;
            const mode = prompt('Режим: Access или Trunk (локальная метка):', 'Access');
            if (mode === null) return;
            try {
                const res = await apiFetch(`/devices/${window.currentPortDeviceId}/ports/${portNumber}`, {
                    method: 'PUT', body: JSON.stringify({ description, mode })
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Не удалось сохранить порт');
                await loadPortView(window.currentPortDeviceId);
            } catch (error) {
                alert(`Ошибка: ${error.message}`);
            }
        }

        function initPingModal() {
            document.getElementById('pingForm')?.addEventListener('submit', async (e) => {
                e.preventDefault();
                const ip = document.getElementById('pingIp').value.trim();
                const count = Number(document.getElementById('pingCountModal').value);
                const timeout = Number(document.getElementById('pingTimeoutModal').value);
                const resultDiv = document.getElementById('pingResult');
                resultDiv.innerHTML = '<div class="spinner-border spinner-border-sm"></div> Выполняется...';
                try {
                    const res = await apiFetch('/ping', {
                        method: 'POST',
                        body: JSON.stringify({ ip, count, timeout })
                    });
                    if (!res.ok) throw new Error(await apiError(res, 'Ошибка выполнения ping'));
                    const data = await res.json();
                    resultDiv.innerHTML = `<div class="ping-output"><strong>${data.alive ? 'Устройство доступно' : 'Ответ не получен'}</strong><span>${escapeHtml(data.output || 'Нет вывода')}</span></div>`;
                } catch (err) {
                    resultDiv.innerHTML = `<div class="text-danger">Ошибка: ${err.message}</div>`;
                }
            });
        }

        // ---------- Запуск приложения ----------
        document.addEventListener('DOMContentLoaded', function() {
            configureRegistration();
            document.getElementById('userEditForm')?.addEventListener('submit', saveUserChanges);
            const token = localStorage.getItem('access_token');
            if (token) {
                fetch(`${API_BASE}/auth/me`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                })
                .then(res => {
                    if (!res.ok) throw new Error('Invalid token');
                    return res.json();
                })
                .then(user => {
                    currentUser = user;
                    document.getElementById('userDisplay').textContent = user.username;
                    document.getElementById('headerUser').textContent = user.username;
                    document.getElementById('userRole').textContent = user.role;
                    showMainApp();
                    loadPage('dashboard');
                    initPingModal();
                    apiFetch('/operations/settings').then(response => response.ok ? response.json() : null).then(settings => { if (settings) pingDefaults = { count: settings.ping_count, timeout: settings.ping_timeout_seconds }; });
                })
                .catch(() => {
                    localStorage.removeItem('access_token');
                    showLoginPage();
                });
            } else {
                showLoginPage();
            }
        });
