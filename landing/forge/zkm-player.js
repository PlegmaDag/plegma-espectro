/**
 * ZKM PLAYER — Web Component Embeddable
 * PLEGMA LABS | ZKM Protocol V1.0
 *
 * Uso:
 *   <script src="zkm-player.js"></script>
 *   <zkm-img src="arquivo.zkm" width="400"></zkm-img>
 *
 * Verifica a prova SHA-256 no carregamento.
 * Anima com timing fiel ao original + efeito visual ZKM.
 */

(function() {
    'use strict';

    // =========================================================================
    // CONSTANTES DO PROTOCOLO
    // =========================================================================
    const ZKM_MAGIC       = [90, 75, 77, 49]; // "ZKM1"
    const HEADER_SIZE     = 13;
    const PROOF_SIZE      = 32;
    const BLOCK_SIZE      = 8;  // x[2] y[2] R[1] G[1] B[1] A[1]
    const FLAG_ANIMATED   = 1;

    // Efeito visual ZKM: ciano (#00F2FF) em baixa opacidade sobre os pixels
    const ZKM_TINT_COLOR  = 'rgba(0, 242, 255, 0.08)';
    const ZKM_SCAN_COLOR  = 'rgba(0, 242, 255, 0.04)';
    const ZKM_GLOW_COLOR  = 'rgba(0, 242, 255, 0.15)';

    // =========================================================================
    // LEITOR DO FORMATO BINÁRIO .zkm
    // =========================================================================
    function parseZKM(buffer) {
        const view  = new DataView(buffer);
        const bytes = new Uint8Array(buffer);

        // Valida magic bytes "ZKM1"
        for (let i = 0; i < 4; i++) {
            if (bytes[i] !== ZKM_MAGIC[i]) {
                throw new Error('Arquivo inválido: magic bytes incorretos. Esperado ZKM1.');
            }
        }

        const width      = view.getUint16(4,  false);
        const height     = view.getUint16(6,  false);
        const step       = bytes[8];
        const totalFrames= bytes[9];
        const flags      = bytes[10];
        const isAnimated = (flags & FLAG_ANIMATED) !== 0;

        // Separa payload da prova
        const payloadEnd  = buffer.byteLength - PROOF_SIZE;
        const payloadView = new Uint8Array(buffer, 0, payloadEnd);
        const proofStored = new Uint8Array(buffer, payloadEnd, PROOF_SIZE);

        // Lê frames
        let offset = HEADER_SIZE;
        const frames = [];

        for (let f = 0; f < totalFrames; f++) {
            if (offset + 6 > payloadEnd) break;

            const delayMs   = view.getUint16(offset, false); offset += 2;
            const blockCount= view.getUint32(offset, false); offset += 4;
            const blocks    = [];

            for (let b = 0; b < blockCount; b++) {
                if (offset + BLOCK_SIZE > payloadEnd) break;
                blocks.push({
                    x: view.getUint16(offset,   false),
                    y: view.getUint16(offset+2, false),
                    r: bytes[offset+4],
                    g: bytes[offset+5],
                    b: bytes[offset+6],
                    a: bytes[offset+7] / 255
                });
                offset += BLOCK_SIZE;
            }

            frames.push({ delayMs, blocks });
        }

        return { width, height, step, isAnimated, frames, payloadView, proofStored };
    }

    // =========================================================================
    // VERIFICAÇÃO DA PROVA SHA-256
    // =========================================================================
    async function verifyProof(payloadView, proofStored) {
        try {
            const hashBuffer = await crypto.subtle.digest('SHA-256', payloadView);
            const hashBytes  = new Uint8Array(hashBuffer);
            for (let i = 0; i < PROOF_SIZE; i++) {
                if (hashBytes[i] !== proofStored[i]) return false;
            }
            return true;
        } catch (e) {
            return false;
        }
    }

    // =========================================================================
    // EFEITO ZKM: scanlines + glow ciano
    // =========================================================================
    function applyZKMEffect(ctx, width, height) {
        // Scanlines horizontais sutis
        for (let y = 0; y < height; y += 4) {
            ctx.fillStyle = ZKM_SCAN_COLOR;
            ctx.fillRect(0, y, width, 1);
        }
        // Vinheta ciano nas bordas
        const grad = ctx.createRadialGradient(
            width/2, height/2, height * 0.3,
            width/2, height/2, height * 0.8
        );
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(1, ZKM_GLOW_COLOR);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, width, height);
    }

    // =========================================================================
    // ANIMAÇÃO DE MONTAGEM (primeiro carregamento)
    // Pixels aparecem gradualmente da esquerda para direita — efeito "forge"
    // =========================================================================
    function playMountAnimation(ctx, frame, width, height, step, onComplete) {
        const blocks   = frame.blocks;
        const total    = blocks.length;
        const perTick  = Math.max(1, Math.floor(total / 40)); // 40 ticks = ~660ms
        let drawn      = 0;

        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, width, height);

        function tick() {
            const end = Math.min(drawn + perTick, total);
            for (let i = drawn; i < end; i++) {
                const { x, y, r, g, b, a } = blocks[i];
                ctx.fillStyle = `rgba(${r},${g},${b},${a})`;
                ctx.fillRect(x, y, step, step);
            }
            drawn = end;

            if (drawn < total) {
                requestAnimationFrame(tick);
            } else {
                applyZKMEffect(ctx, width, height);
                onComplete();
            }
        }
        requestAnimationFrame(tick);
    }

    // =========================================================================
    // RENDERIZA UM FRAME (sem animação de montagem)
    // =========================================================================
    function renderFrame(ctx, frame, width, height, step) {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, width, height);

        const { blocks } = frame;
        for (let i = 0; i < blocks.length; i++) {
            const { x, y, r, g, b, a } = blocks[i];
            ctx.fillStyle = `rgba(${r},${g},${b},${a})`;
            ctx.fillRect(x, y, step, step);
        }
        applyZKMEffect(ctx, width, height);
    }

    // =========================================================================
    // WEB COMPONENT <zkm-img>
    // =========================================================================
    class ZkmImg extends HTMLElement {
        constructor() {
            super();
            this._animTimer  = null;
            this._frameIndex = 0;
            this._data       = null;
            this.attachShadow({ mode: 'open' });
        }

        static get observedAttributes() { return ['src', 'width', 'height']; }

        attributeChangedCallback(name) {
            if (name === 'src') this._load();
        }

        connectedCallback() {
            this._render();
            if (this.getAttribute('src')) this._load();
        }

        disconnectedCallback() {
            this._stopAnimation();
        }

        _render() {
            const w = this.getAttribute('width')  || '100%';
            const h = this.getAttribute('height') || 'auto';

            this.shadowRoot.innerHTML = `
                <style>
                    :host { display: inline-block; }
                    .zkm-wrapper {
                        position: relative;
                        display: inline-block;
                        width: ${isNaN(w) ? w : w + 'px'};
                    }
                    canvas {
                        display: block;
                        width: 100%;
                        height: auto;
                        image-rendering: pixelated;
                    }
                    .zkm-badge {
                        position: absolute;
                        bottom: 6px; right: 6px;
                        font-family: monospace;
                        font-size: 9px;
                        color: rgba(0,242,255,0.6);
                        letter-spacing: 2px;
                        pointer-events: none;
                        text-shadow: 0 0 6px rgba(0,242,255,0.8);
                    }
                    .zkm-badge.verified { color: rgba(35,209,139,0.8); }
                    .zkm-badge.invalid  { color: rgba(255,51,51,0.8);  }
                    .zkm-loading {
                        font-family: monospace; font-size: 10px;
                        color: rgba(0,242,255,0.5);
                        padding: 20px; letter-spacing: 3px;
                        text-transform: uppercase;
                    }
                    .zkm-error {
                        font-family: monospace; font-size: 10px;
                        color: rgba(255,51,51,0.7);
                        padding: 20px; letter-spacing: 2px;
                    }
                </style>
                <div class="zkm-wrapper">
                    <div class="zkm-loading">ZKM: Carregando...</div>
                </div>
            `;
        }

        async _load() {
            const src = this.getAttribute('src');
            if (!src) return;

            this._stopAnimation();
            const wrapper = this.shadowRoot.querySelector('.zkm-wrapper');
            wrapper.innerHTML = '<div class="zkm-loading">ZKM: Verificando prova...</div>';

            try {
                const response = await fetch(src);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const buffer = await response.arrayBuffer();

                const data = parseZKM(buffer);
                const valid = await verifyProof(data.payloadView, data.proofStored);

                this._data = data;
                this._frameIndex = 0;

                // Monta o canvas
                const canvas = document.createElement('canvas');
                canvas.width  = data.width;
                canvas.height = data.height;
                const ctx = canvas.getContext('2d');

                const badge = document.createElement('div');
                badge.className = 'zkm-badge' + (valid ? ' verified' : ' invalid');
                badge.textContent = valid ? 'ZK-VERIFIED ✓' : 'PROVA INVÁLIDA ✗';

                wrapper.innerHTML = '';
                wrapper.appendChild(canvas);
                wrapper.appendChild(badge);

                // Animação de montagem no primeiro frame
                playMountAnimation(ctx, data.frames[0], data.width, data.height, data.step, () => {
                    if (data.isAnimated && data.frames.length > 1) {
                        this._startAnimation(ctx, data);
                    }
                });

            } catch (e) {
                wrapper.innerHTML = `<div class="zkm-error">ZKM ERROR: ${e.message}</div>`;
            }
        }

        _startAnimation(ctx, data) {
            this._frameIndex = 0;
            const next = () => {
                this._frameIndex = (this._frameIndex + 1) % data.frames.length;
                const frame = data.frames[this._frameIndex];
                renderFrame(ctx, frame, data.width, data.height, data.step);
                this._animTimer = setTimeout(next, frame.delayMs);
            };
            const firstDelay = data.frames[0].delayMs;
            this._animTimer = setTimeout(next, firstDelay);
        }

        _stopAnimation() {
            if (this._animTimer) {
                clearTimeout(this._animTimer);
                this._animTimer = null;
            }
        }
    }

    // Registra o Web Component
    if (!customElements.get('zkm-img')) {
        customElements.define('zkm-img', ZkmImg);
    }

    // Expõe API global para uso programático
    window.ZKM = {
        version: '1.0',
        protocol: 'ZKM1',
        /**
         * Renderiza um .zkm em qualquer elemento
         * ZKM.render('arquivo.zkm', '#meu-div')
         */
        render(src, selector) {
            const el  = document.querySelector(selector);
            if (!el) return console.error('ZKM: elemento não encontrado:', selector);
            const img = document.createElement('zkm-img');
            img.setAttribute('src', src);
            img.setAttribute('width', el.offsetWidth || '400');
            el.appendChild(img);
        }
    };

})();
