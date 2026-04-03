// =============================================================================
// TELEMETRY.JS — Visualizador DAG em Tempo Real
//
// Conectado à API V1.0 (porta 8080):
//   GET /api/status    → nos_ativos → escala o número de partículas
//   GET /api/lastBlock → last_vertex_hash → exibe no visualizador
//
// Regra do Estatuto §2.1 respeitada:
//   Cada nó (partícula) conecta no máximo 5 vizinhos — igual ao protocolo DAG
// =============================================================================

const canvas = document.getElementById('dag-canvas');
const ctx = canvas.getContext('2d');

let particles = [];
let networkStatus = { nos_ativos: 40, last_hash: '---', peso_zk: '0 KB' };

// Busca dados reais da API V1.0
async function fetchNetworkStatus() {
    try {
        const res = await fetch('http://localhost:8080/api/status');
        const data = await res.json();
        networkStatus.nos_ativos = data.nos_ativos || 40;

        // Atualiza o contador de nós no card
        const nodeEl = document.getElementById('nodeCount');
        if (nodeEl) nodeEl.innerText = data.nos_ativos.toLocaleString('pt-BR');

        // Atualiza indicador de status no visualizador
        const statusEl = document.getElementById('network-status');
        if (statusEl) statusEl.innerText = data.status === 'ONLINE'
            ? 'REDE: ONLINE ●'
            : 'REDE: OFFLINE ○';

        // Reescala partículas se a contagem mudou significativamente
        const target = Math.min(Math.max(Math.floor(networkStatus.nos_ativos / 100), 20), 80);
        if (Math.abs(particles.length - target) > 5) {
            initParticles(target);
        }
    } catch (e) {
        // API offline — mantém simulação local
    }
}

async function fetchLastBlock() {
    try {
        const res = await fetch('http://localhost:8080/api/lastBlock');
        const data = await res.json();
        networkStatus.last_hash = data.last_vertex_hash || '---';
        networkStatus.peso_zk = data.peso_zk || '0 KB';

        // Injeta o hash real no feed de transações
        const feed = document.getElementById('txFeed');
        const total = document.getElementById('txTotal');
        if (feed) {
            const item = document.createElement('div');
            item.className = 'tx-item';
            const hash = networkStatus.last_hash.substring(0, 16) + '...';
            item.innerHTML = `<span style="color:var(--text-dim)">${hash}</span>
                              <span style="color:var(--accent-cyan)">ZK: ${networkStatus.peso_zk}</span>`;
            feed.appendChild(item);
            if (feed.children.length > 12) feed.removeChild(feed.firstChild);
        }
        if (total) {
            const count = parseInt(total.innerText) + 1;
            total.innerText = count.toString().padStart(6, '0');
        }
    } catch (e) {
        // API offline — feed continua com simulação
        injectSimulatedTx();
    }
}

function injectSimulatedTx() {
    const feed = document.getElementById('txFeed');
    const total = document.getElementById('txTotal');
    if (!feed) return;
    const item = document.createElement('div');
    item.className = 'tx-item';
    const amount = (Math.random() * 5).toFixed(2);
    item.innerHTML = `<span>TX_ANONYMOUS</span>
                      <span style="color:var(--accent-cyan)">+${amount} $PLG</span>`;
    feed.appendChild(item);
    if (feed.children.length > 12) feed.removeChild(feed.firstChild);
    if (total) {
        const count = parseInt(total.innerText) + 1;
        total.innerText = count.toString().padStart(6, '0');
    }
}

// =============================================================================
// PARTÍCULAS — Visualização da Topologia DAG
// Cores: Ciano = vértice novo (tip) | Âmbar = vértice ancorado (confirmado)
// =============================================================================
class Particle {
    constructor() { this.reset(); }

    reset() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.vx = (Math.random() - 0.5) * 1.5;
        this.vy = (Math.random() - 0.5) * 1.5;
        this.size = Math.random() * 2 + 1;
        // Ciano = tip (não confirmado) | Âmbar = ancorado (confirmado)
        this.color = Math.random() > 0.3 ? '#00F2FF' : '#FFCC00';
        this.connections = 0; // Contador de conexões — máximo 5 (Estatuto §2.1)
    }

    update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        this.connections = 0; // Reseta contador a cada frame
    }

    draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = this.color;
        ctx.shadowBlur = 10;
        ctx.shadowColor = this.color;
        ctx.fill();
    }
}

function initParticles(count) {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    particles = [];
    for (let i = 0; i < count; i++) particles.push(new Particle());
}

function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particles.forEach(p => p.update());

    // Desenha conexões respeitando o limite de 5 pais por nó (Estatuto §2.1)
    particles.forEach(p => {
        p.draw();
        // Ordena vizinhos por distância e pega os mais próximos até 5
        const vizinhos = particles
            .filter(p2 => p2 !== p)
            .map(p2 => ({ p2, dist: Math.hypot(p.x - p2.x, p.y - p2.y) }))
            .filter(({ dist }) => dist < 120)
            .sort((a, b) => a.dist - b.dist)
            .slice(0, 5); // Máximo 5 conexões — alinhado ao protocolo DAG

        vizinhos.forEach(({ p2, dist }) => {
            if (p.connections >= 5 || p2.connections >= 5) return;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(0, 242, 255, ${1 - dist / 120})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
            p.connections++;
            p2.connections++;
        });
    });

    requestAnimationFrame(animate);
}

// Reescala o canvas no resize sem recriar partículas do zero
window.addEventListener('resize', () => {
    const oldW = canvas.width;
    const oldH = canvas.height;
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    // Reposiciona partículas proporcionalmente
    particles.forEach(p => {
        p.x = (p.x / oldW) * canvas.width;
        p.y = (p.y / oldH) * canvas.height;
    });
});

// Polling da API a cada 3 segundos
fetchNetworkStatus();
fetchLastBlock();
setInterval(fetchNetworkStatus, 3000);
setInterval(fetchLastBlock, 3000);

// Inicia visualização
initParticles(40);
animate();
