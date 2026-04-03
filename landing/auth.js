/**
 * AUTH.JS — Módulo Central de Autenticação PLEGMA
 * Single Sign-On via QR Challenge/Response + Dilithium3
 *
 * Uso em qualquer página:
 *   <script src="/auth.js"></script>
 *
 * API pública:
 *   PlegmaAuth.init(options)       — inicializa e detecta sessão existente
 *   PlegmaAuth.openModal()         — abre modal de login QR
 *   PlegmaAuth.logout()            — encerra sessão
 *   PlegmaAuth.getSession()        — retorna {plg_address, token} ou null
 *   PlegmaAuth.isConnected()       — boolean
 *   PlegmaAuth.isAdmin()           — boolean
 *   PlegmaAuth.onLogin(callback)   — callback chamado ao autenticar
 *   PlegmaAuth.onLogout(callback)  — callback chamado ao desconectar
 */

(function() {
'use strict';

// ============================================================================
// CONFIG
// ============================================================================
const AUTH_SERVER = 'https://api.plegmadag.com';
const SESSION_KEY = 'plg_session';
const ADMIN_PLG   = 'PLG0000000000000000000000000000000000000000'; // trocar pelo endereço real
const QR_LIB_URL  = 'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js';
const SESSION_TTL  = 86400000; // 24h em ms

// ============================================================================
// ESTADO INTERNO
// ============================================================================
let _session      = null;  // { plg_address, token, created_at }
let _authNonce    = null;
let _timerInterval= null;
let _pollInterval = null;
let _timeLeft     = 120;
let _loginCbs     = [];
let _logoutCbs    = [];
let _options      = {};

// ============================================================================
// SESSÃO
// ============================================================================
function _saveSession(plgAddress, token) {
    const sess = { plg_address: plgAddress, token, created_at: Date.now() };
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(sess)); } catch(e) {}
    _session = sess;
}

function _loadSession() {
    try {
        const raw = sessionStorage.getItem(SESSION_KEY);
        if (!raw) return null;
        const sess = JSON.parse(raw);
        if (!sess.plg_address || !sess.created_at) return null;
        if (Date.now() - sess.created_at > SESSION_TTL) {
            sessionStorage.removeItem(SESSION_KEY);
            return null;
        }
        return sess;
    } catch(e) { return null; }
}

function _clearSession() {
    try { sessionStorage.removeItem(SESSION_KEY); } catch(e) {}
    _session = null;
}

// ============================================================================
// INJEÇÃO DO MODAL E ESTILOS
// ============================================================================
function _injectStyles() {
    if (document.getElementById('plg-auth-styles')) return;
    const style = document.createElement('style');
    style.id = 'plg-auth-styles';
    style.textContent = `
        #plg-auth-overlay {
            display: none; position: fixed; inset: 0;
            background: rgba(0,0,0,0.92);
            backdrop-filter: blur(10px);
            z-index: 9999;
            justify-content: center; align-items: center;
            padding: 20px;
            font-family: 'Space Mono', monospace;
        }
        #plg-auth-overlay.open { display: flex; }

        #plg-auth-modal {
            background: #050a14;
            border: 1px solid rgba(0,242,255,0.3);
            border-radius: 8px; padding: 32px;
            width: 100%; max-width: 400px;
            text-align: center;
            position: relative;
        }

        #plg-auth-modal h3 {
            font-family: 'Space Mono', monospace;
            font-size: 0.85rem; font-weight: 700;
            color: #00F2FF; letter-spacing: 3px;
            text-transform: uppercase;
            margin: 0 0 20px; text-shadow: 0 0 10px rgba(0,242,255,0.5);
        }

        .plg-qr-wrap {
            background: #fff; padding: 14px;
            border-radius: 8px; display: inline-block;
            margin-bottom: 14px; line-height: 0;
        }

        #plg-qr-loading {
            width: 200px; height: 200px;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.6rem; color: #888; letter-spacing: 2px;
        }

        #plg-qr-rendered { line-height: 0; }
        #plg-qr-rendered img { display: block; }

        .plg-nonce-display {
            font-size: 0.6rem; color: rgba(0,242,255,0.5);
            letter-spacing: 2px; margin-bottom: 10px;
        }

        .plg-timer-wrap { margin-bottom: 14px; }
        .plg-timer-label {
            font-size: 0.55rem; color: #64748b;
            letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px;
        }
        .plg-timer-bar-bg {
            width: 100%; height: 2px;
            background: rgba(0,242,255,0.1);
            border-radius: 2px; overflow: hidden;
        }
        #plg-timer-bar {
            height: 100%; width: 100%;
            background: #00F2FF;
            transition: width 1s linear, background 1s;
        }

        #plg-auth-status {
            font-size: 0.65rem; color: #64748b;
            letter-spacing: 1px; margin-bottom: 16px;
            padding: 8px 12px;
            border: 1px solid rgba(0,242,255,0.1);
            border-radius: 4px; background: rgba(0,0,0,0.3);
            line-height: 1.5; min-height: 36px;
        }

        .plg-https-warn {
            font-size: 0.6rem; color: #f59e0b;
            border: 1px solid rgba(245,158,11,0.3);
            border-radius: 4px; padding: 8px;
            margin-bottom: 12px; letter-spacing: 1px;
            display: none;
        }
        .plg-https-warn.show { display: block; }

        .plg-auth-actions {
            display: flex; gap: 10px; margin-top: 4px;
        }

        .plg-btn {
            flex: 1; font-family: 'Space Mono', monospace;
            font-size: 0.6rem; letter-spacing: 1px;
            text-transform: uppercase; padding: 10px;
            border-radius: 4px; cursor: pointer;
            transition: all 0.2s; text-decoration: none;
            display: flex; align-items: center; justify-content: center;
        }
        .plg-btn-cancel {
            background: transparent; color: #64748b;
            border: 1px solid rgba(100,116,139,0.3);
        }
        .plg-btn-cancel:hover { border-color: #64748b; color: #94a3b8; }

        .plg-btn-sim {
            background: rgba(0,242,255,0.08);
            color: #00F2FF;
            border: 1px solid rgba(0,242,255,0.3);
        }
        .plg-btn-sim:hover { background: rgba(0,242,255,0.15); }

        /* Tela de sucesso */
        #plg-auth-success { display: none; }
        #plg-auth-success.show { display: block; }
        #plg-auth-qr-screen.hide { display: none; }

        .plg-success-icon {
            font-size: 3rem; margin-bottom: 12px; color: #23d18b;
            text-shadow: 0 0 20px rgba(35,209,139,0.5);
        }
        .plg-success-label {
            font-size: 0.75rem; color: #23d18b;
            letter-spacing: 3px; font-weight: 700;
            margin-bottom: 14px; text-transform: uppercase;
        }
        .plg-success-addr {
            font-size: 0.6rem; color: #94a3b8;
            word-break: break-all; letter-spacing: 1px;
            border: 1px solid rgba(0,242,255,0.15);
            border-radius: 4px; padding: 10px;
            background: rgba(0,0,0,0.3); margin-bottom: 20px;
        }
        .plg-btn-enter {
            width: 100%; background: #23d18b; color: #000;
            border: none; padding: 13px; border-radius: 4px;
            font-family: 'Space Mono', monospace;
            font-size: 0.7rem; font-weight: 700;
            letter-spacing: 2px; text-transform: uppercase;
            cursor: pointer; transition: all 0.2s;
        }
        .plg-btn-enter:hover { filter: brightness(1.1); }

        /* Botão wallet nav — estilo injetado dinamicamente */
        .plg-wallet-btn {
            font-family: 'Space Mono', monospace;
            font-size: 0.65rem; letter-spacing: 1px;
            padding: 7px 14px; border-radius: 4px;
            border: 1px solid rgba(0,242,255,0.3);
            background: rgba(0,242,255,0.08);
            color: #00F2FF; cursor: pointer;
            transition: all 0.2s; text-transform: uppercase;
        }
        .plg-wallet-btn:hover {
            background: rgba(0,242,255,0.15);
            box-shadow: 0 0 8px rgba(0,242,255,0.2);
        }
        .plg-wallet-btn.connected {
            border-color: rgba(35,209,139,0.4);
            color: #23d18b;
            background: rgba(35,209,139,0.08);
        }
    `;
    document.head.appendChild(style);
}

function _injectModal() {
    if (document.getElementById('plg-auth-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'plg-auth-overlay';
    overlay.innerHTML = `
        <div id="plg-auth-modal">
            <h3>[ CONECTAR CARTEIRA ]</h3>

            <div id="plg-auth-qr-screen">
                <p style="font-size:0.7rem;color:#94a3b8;margin-bottom:16px;line-height:1.8;letter-spacing:1px;">
                    Escaneie com o app PLEGMA<br>e confirme com biometria.
                </p>

                <div class="plg-qr-wrap">
                    <div id="plg-qr-loading">GERANDO...</div>
                    <div id="plg-qr-rendered"></div>
                </div>

                <div class="plg-nonce-display">
                    NONCE: <span id="plg-nonce-val">--</span>
                </div>

                <div class="plg-timer-wrap">
                    <div class="plg-timer-label">
                        Expira em <span id="plg-timer-num">120</span>s
                    </div>
                    <div class="plg-timer-bar-bg">
                        <div id="plg-timer-bar"></div>
                    </div>
                </div>

                <div id="plg-auth-status">⬡ Aguardando leitura do QR...</div>

                <div class="plg-https-warn" id="plg-https-warn">
                    ⚠ Use HTTPS em produção para segurança máxima.
                </div>

                <div class="plg-auth-actions">
                    <button class="plg-btn plg-btn-cancel" onclick="PlegmaAuth.closeModal()">
                        CANCELAR
                    </button>
                    <a href="/auth-simulator.html" target="_blank" class="plg-btn plg-btn-sim">
                        SIMULADOR →
                    </a>
                </div>
            </div>

            <div id="plg-auth-success">
                <div class="plg-success-icon">✓</div>
                <div class="plg-success-label">AUTENTICADO</div>
                <div class="plg-success-addr" id="plg-success-addr">--</div>
                <button class="plg-btn-enter" onclick="PlegmaAuth.closeModal()">
                    ENTRAR →
                </button>
            </div>
        </div>
    `;

    overlay.addEventListener('click', e => {
        if (e.target === overlay) PlegmaAuth.closeModal();
    });

    document.body.appendChild(overlay);
}

// ============================================================================
// QR CODE
// ============================================================================
function _loadQRLib() {
    return new Promise((resolve, reject) => {
        if (window.QRCode) { resolve(); return; }
        const s = document.createElement('script');
        s.src = QR_LIB_URL;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

async function _renderQR(message) {
    await _loadQRLib();
    const container = document.getElementById('plg-qr-rendered');
    const loading   = document.getElementById('plg-qr-loading');
    if (!container) return;
    // Limpa render anterior
    container.innerHTML = '';
    // qrcodejs API: new QRCode(element, options) — síncrono
    new QRCode(container, {
        text        : message,
        width       : 200,
        height      : 200,
        colorDark   : '#000000',
        colorLight  : '#ffffff',
        correctLevel: QRCode.CorrectLevel.M
    });
    if (loading) loading.style.display = 'none';
}

// ============================================================================
// CHALLENGE/RESPONSE
// ============================================================================
// Detecta se o usuário está num dispositivo mobile
function _isMobile() {
    return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

async function _startChallenge() {
    _stopTimers();
    _timeLeft = 120;
    _resetQR();

    // Mostra tela QR, esconde sucesso
    const qrScreen  = document.getElementById('plg-auth-qr-screen');
    const success   = document.getElementById('plg-auth-success');
    if (qrScreen) qrScreen.classList.remove('hide');
    if (success)  success.classList.remove('show');

    // Aviso HTTPS
    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
        const warn = document.getElementById('plg-https-warn');
        if (warn) warn.classList.add('show');
    }

    try {
        const res  = await fetch(`${AUTH_SERVER}/api/auth/challenge`);
        const data = await res.json();
        _authNonce = data.nonce;

        const nonceEl = document.getElementById('plg-nonce-val');
        if (nonceEl) nonceEl.textContent = _authNonce.substring(0,8) + '...' + _authNonce.slice(-4);

        if (_isMobile()) {
            // Mobile: tenta abrir o app PLEGMA diretamente via deep link
            // Se o app estiver instalado, iOS/Android abre e pede biometria
            // Se não estiver instalado, após 1.8s mostra o QR como fallback
            _setStatus('⬡ Abrindo app PLEGMA...', '#00F2FF');
            window.location = data.message; // plegma://auth?nonce=XXX&site=plegmadag.com
            setTimeout(async () => {
                // Se chegou aqui, o app não abriu — mostra QR como fallback
                _setStatus('⬡ App não encontrado. Escaneie o QR ou use o simulador.', '#f59e0b');
                await _renderQR(data.message);
            }, 1800);
        } else {
            // Desktop: mostra QR normalmente
            await _renderQR(data.message);
        }

        _startTimer();
        _startPolling(_authNonce);

    } catch(e) {
        _setStatus('⬡ Auth server offline. Use o simulador para testar.', '#f59e0b');
        // QR de demo
        try {
            await _renderQR('plegma://auth?nonce=DEMO_OFFLINE&site=plegmadag.com');
            const nonceEl = document.getElementById('plg-nonce-val');
            if (nonceEl) nonceEl.textContent = 'DEMO_OFFLINE';
        } catch(e2) {}
    }
}

function _resetQR() {
    const container = document.getElementById('plg-qr-rendered');
    const loading   = document.getElementById('plg-qr-loading');
    if (container) container.innerHTML = '';
    if (loading)   { loading.style.display = 'flex'; loading.textContent = 'GERANDO...'; }
    _updateTimerBar(120, 120);
    const timerNum = document.getElementById('plg-timer-num');
    if (timerNum) timerNum.textContent = '120';
}

function _startTimer() {
    _timerInterval = setInterval(() => {
        _timeLeft--;
        const el = document.getElementById('plg-timer-num');
        if (el) el.textContent = _timeLeft;
        _updateTimerBar(_timeLeft, 120);

        if (_timeLeft <= 0) {
            _stopTimers();
            _setStatus('⬡ Código expirado. Feche e tente novamente.', '#ef4444');
        }
    }, 1000);
}

function _startPolling(nonce) {
    _pollInterval = setInterval(async () => {
        try {
            const res  = await fetch(`${AUTH_SERVER}/api/auth/status?nonce=${nonce}`);
            const data = await res.json();

            if (data.status === 'verified') {
                _stopTimers();
                _onSuccess(data.plg_address, data.token);
            } else if (data.status === 'expired') {
                _stopTimers();
                _setStatus('⬡ Código expirado. Feche e tente novamente.', '#ef4444');
            } else {
                const rem = data.remaining || _timeLeft;
                _setStatus(`⬡ Aguardando leitura do QR... (${rem}s)`, '#64748b');
            }
        } catch(e) { /* servidor offline — polling silencioso */ }
    }, 2000);
}

function _stopTimers() {
    clearInterval(_timerInterval);
    clearInterval(_pollInterval);
    _timerInterval = null;
    _pollInterval  = null;
}

function _updateTimerBar(current, total) {
    const bar = document.getElementById('plg-timer-bar');
    if (!bar) return;
    const pct = (current / total) * 100;
    bar.style.width      = pct + '%';
    bar.style.background = pct > 50 ? '#00F2FF' : pct > 20 ? '#f59e0b' : '#ef4444';
}

function _setStatus(msg, color) {
    const el = document.getElementById('plg-auth-status');
    if (el) { el.textContent = msg; el.style.color = color || '#64748b'; }
}

// ============================================================================
// SUCESSO — chamado quando o polling confirma a verificação
// ============================================================================
function _onSuccess(plgAddress, token) {
    _saveSession(plgAddress, token || 'verified');

    // Tela de sucesso no modal
    const qrScreen = document.getElementById('plg-auth-qr-screen');
    const success  = document.getElementById('plg-auth-success');
    const addrEl   = document.getElementById('plg-success-addr');
    if (qrScreen) qrScreen.classList.add('hide');
    if (success)  success.classList.add('show');
    if (addrEl)   addrEl.textContent = plgAddress;

    // Atualiza todos os botões de carteira na página
    _updateWalletButtons(plgAddress);

    // Dispara callbacks registrados
    _loginCbs.forEach(cb => { try { cb(plgAddress); } catch(e) {} });
}

function _updateWalletButtons(plgAddress) {
    const label = plgAddress.substring(0,6) + '...' + plgAddress.slice(-4);
    document.querySelectorAll('[data-plg-wallet-btn]').forEach(btn => {
        btn.textContent = label;
        btn.classList.add('connected');
    });
}

// ============================================================================
// API PÚBLICA
// ============================================================================
const PlegmaAuth = {

    /**
     * Inicializa o módulo de auth.
     * Chame no DOMContentLoaded de cada página.
     *
     * @param {object} options
     *   onLogin(plgAddress)  — callback ao autenticar
     *   onLogout()           — callback ao desconectar
     *   adminPlg             — endereço do admin (sobrescreve o padrão)
     */
    init(options = {}) {
        _options = options;
        if (options.onLogin)  _loginCbs.push(options.onLogin);
        if (options.onLogout) _logoutCbs.push(options.onLogout);
        if (options.adminPlg) Object.assign(this, { _adminPlg: options.adminPlg });

        _injectStyles();
        _injectModal();

        // Restaura sessão existente automaticamente
        const saved = _loadSession();
        if (saved) {
            _session = saved;
            _updateWalletButtons(saved.plg_address);
            _loginCbs.forEach(cb => { try { cb(saved.plg_address); } catch(e) {} });
        }

        // Escuta autenticação vinda do simulador ou do app mobile (BroadcastChannel)
        try {
            const _bc = new BroadcastChannel('plg_auth_channel');
            _bc.onmessage = (e) => {
                if (e.data && e.data.type === 'LOGIN' && e.data.plg_address) {
                    _stopTimers();
                    _onSuccess(e.data.plg_address, e.data.token || 'broadcast');
                    // Fecha o modal se estiver aberto
                    const overlay = document.getElementById('plg-auth-overlay');
                    if (overlay) overlay.classList.remove('open');
                    document.body.style.overflow = '';
                }
            };
        } catch(e) {}
    },

    openModal() {
        const overlay = document.getElementById('plg-auth-overlay');
        if (!overlay) { _injectStyles(); _injectModal(); }
        document.getElementById('plg-auth-overlay').classList.add('open');
        document.body.style.overflow = 'hidden';
        _startChallenge();
    },

    closeModal() {
        const overlay = document.getElementById('plg-auth-overlay');
        if (overlay) overlay.classList.remove('open');
        document.body.style.overflow = '';
        _stopTimers();
    },

    logout() {
        _stopTimers();
        _clearSession();
        document.querySelectorAll('[data-plg-wallet-btn]').forEach(btn => {
            btn.textContent = 'Conectar Carteira';
            btn.classList.remove('connected');
        });
        _logoutCbs.forEach(cb => { try { cb(); } catch(e) {} });

        // Notifica o servidor
        if (_session) {
            fetch(`${AUTH_SERVER}/api/auth/logout`, {
                method : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ plg_address: _session.plg_address, token: _session.token })
            }).catch(() => {});
        }
        _session = null;
    },

    getSession()   { return _session ? { ..._session } : null; },
    isConnected()  { return !!_session; },
    isAdmin()      {
        const adminAddr = (this._adminPlg || ADMIN_PLG);
        return !!_session && _session.plg_address === adminAddr;
    },
    onLogin(cb)    { _loginCbs.push(cb); },
    onLogout(cb)   { _logoutCbs.push(cb); },

    // Cria um botão de carteira padronizado e o injeta num elemento
    mountWalletButton(element, options = {}) {
        if (!element) return;
        const btn = document.createElement('button');
        btn.setAttribute('data-plg-wallet-btn', '');
        btn.className   = 'plg-wallet-btn' + (options.className ? ' ' + options.className : '');
        btn.textContent = _session
            ? _session.plg_address.substring(0,6) + '...' + _session.plg_address.slice(-4)
            : (options.label || 'Conectar Carteira');
        if (_session) btn.classList.add('connected');

        btn.addEventListener('click', () => {
            if (PlegmaAuth.isConnected()) {
                if (confirm('Desconectar carteira?')) PlegmaAuth.logout();
            } else {
                PlegmaAuth.openModal();
            }
        });
        element.appendChild(btn);
        return btn;
    }
};

window.PlegmaAuth = PlegmaAuth;

})();
