import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import threading
import json
import os
import time
from datetime import datetime

# Módulos locais (Já purificados V4.0)
from hardware_detector import detectar_hardware, classificar, calcular_score
from miner_engine import MinerEngine
from miner_server import iniciar_servidor

# Tenta importar qrcode para exibir QR de vínculo
try:
    import qrcode
    from PIL import Image, ImageTk
    QR_OK = True
except ImportError:
    QR_OK = False

# =============================================================================
# CONFIGURAÇÃO VISUAL — Espelho do Dashboard (V4.0)
# =============================================================================
COR = {
    "bg"      : "#060d1a",       # Fundo principal
    "bg2"     : "#0a192f",       # Cards
    "bg3"     : "#0d2040",       # Input/hover
    "cyan"    : "#00F2FF",       # Acento principal
    "cyan_dim": "#00a8b3",       # Acento fraco
    "green"   : "#23d18b",       # Sucesso / online
    "amber"   : "#f59e0b",       # Aviso
    "red"     : "#ef4444",       # Erro / offline
    "purple"  : "#a78bfa",       # V2.0+
    "text"    : "#e2e8f0",       # Texto principal
    "text2"   : "#64748b",       # Texto secundário
    "border"  : "#0f2a45",       # Bordas
}

FONTE_MONO  = ("Courier New", 9)
FONTE_MONO2 = ("Courier New", 8)
FONTE_TITLE = ("Courier New", 11, "bold")
FONTE_VALUE = ("Courier New", 14, "bold")
FONTE_BIG   = ("Courier New", 20, "bold")

CONFIG_FILE = "miner_config.json"
LOG_MAX     = 120   # Máximo de linhas no log


# =============================================================================
# UTILIDADES
# =============================================================================
def carregar_config() -> dict | None:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def salvar_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def formatar_plg(valor: float) -> str:
    return f"{valor:,.4f} $PLG"


# =============================================================================
# LOGO GIF — Carrega e anima o logo.gif em qualquer Label
# =============================================================================
def _carregar_gif(caminho: str, altura: int = 36):
    """
    Carrega um GIF redimensionado para a altura indicada (mantém proporção).
    Retorna (frames, delays) ou (None, None) se falhar.
    """
    if not caminho or not os.path.exists(caminho):
        return None, None
    try:
        from PIL import Image, ImageTk
        img    = Image.open(caminho)
        w0, h0 = img.size
        ratio  = altura / max(h0, 1)
        novo_w = max(1, int(w0 * ratio))
        novo_h = altura

        frames, delays = [], []
        try:
            while True:
                frame = img.copy().convert("RGBA").resize(
                    (novo_w, novo_h), Image.LANCZOS
                )
                frames.append(ImageTk.PhotoImage(frame))
                delays.append(img.info.get("duration", 80))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        if not frames:
            return None, None
        print(f"[+] Logo carregada: {len(frames)} frame(s) @ {novo_w}x{novo_h}px.")
        return frames, delays
    except ImportError:
        print("[!] Pillow não instalado. Execute: python -m pip install pillow")
        return None, None
    except Exception as e:
        print(f"[!] Erro ao carregar logo '{caminho}': {e}")
        return None, None


def _animar_label_gif(widget, frames, delays, idx=0):
    """Anima um Label Tkinter com frames de GIF."""
    if not frames or not widget.winfo_exists():
        return
    widget.config(image=frames[idx])
    widget.image = frames[idx]       # Evita garbage collection
    prox = (idx + 1) % len(frames)
    widget.after(delays[idx], lambda: _animar_label_gif(widget, frames, delays, prox))


LOGO_PATH = None
_base = os.path.dirname(os.path.abspath(__file__))
_candidatos = [
    os.path.join(_base, "logo.gif"),                             # mesma pasta ← principal
    os.path.join(_base, "assets", "img", "logo.gif"),            # miner/assets/img/
    os.path.join(_base, "..", "assets", "img", "logo.gif"),      # um nível acima
    os.path.join(_base, "..", "logo.gif"),                       # pasta pai
]
for _c in _candidatos:
    if os.path.exists(_c):
        LOGO_PATH = os.path.normpath(_c)
        break

if LOGO_PATH:
    print(f"[+] Logo encontrada: {LOGO_PATH}")
else:
    print(f"[!] Logo não encontrada. Certifique-se que 'logo.gif' está em: {_base}")

# Verifica Pillow
try:
    from PIL import Image, ImageTk
    _PIL_OK = True
    print("[+] Pillow disponível — logo animada ativada.")
except ImportError:
    _PIL_OK = False
    print("[!] Pillow não instalado. Execute: pip install pillow")
    print("    Sem Pillow a logo não carrega. Usando ícone texto como fallback.")



class MineradorGUI:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⬡ PLEGMA Minerador V4.0")
        self.root.geometry("1000x680")
        self.root.minsize(860, 580)
        self.root.configure(bg=COR["bg"])

        # Estado
        self.engine    = None
        self.config    = carregar_config()
        self.log_lines = []
        self._after_ids = []

        # Construção
        self._build_window()

        # Protocolo de fechamento
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Inicia na tela correta
        if self.config:
            self._mostrar_painel_principal()
        else:
            self._mostrar_boot()

    # =========================================================================
    # ESTRUTURA BASE
    # =========================================================================
    def _build_window(self):
        self._build_topbar()
        self.container = tk.Frame(self.root, bg=COR["bg"])
        self.container.pack(fill="both", expand=True)

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=COR["bg2"], height=48)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        frames, delays = _carregar_gif(LOGO_PATH, altura=34)
        if frames:
            lbl_logo = tk.Label(bar, bg=COR["bg2"], bd=0, highlightthickness=0)
            lbl_logo.pack(side="left", padx=(14, 6), pady=4)
            _animar_label_gif(lbl_logo, frames, delays)
            tk.Label(bar, text="PLEGMA MINERADOR",
                     font=("Courier New", 12, "bold"),
                     bg=COR["bg2"], fg=COR["cyan"]).pack(side="left")
        else:
            tk.Label(bar, text="⬡ PLEGMA MINERADOR",
                     font=("Courier New", 12, "bold"),
                     bg=COR["bg2"], fg=COR["cyan"]).pack(side="left", padx=20)

        self.lbl_topbar_status = tk.Label(
            bar, text="● AGUARDANDO",
            font=FONTE_MONO, bg=COR["bg2"], fg=COR["text2"]
        )
        self.lbl_topbar_status.pack(side="right", padx=20)

        tk.Label(bar, text="V4.0 · Crystals-Dilithium3",
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
                 ).pack(side="right", padx=10)

        sep = tk.Frame(self.root, bg=COR["border"], height=1)
        sep.pack(fill="x", side="top")

    # =========================================================================
    # TELA DE BOOT (primeiro uso)
    # =========================================================================
    def _mostrar_boot(self):
        self._limpar_container()
        BootScreen(self.container, self._on_boot_completo)

    def _on_boot_completo(self, config: dict):
        salvar_config(config)
        self.config = config
        self._mostrar_painel_principal()

    # =========================================================================
    # PAINEL PRINCIPAL
    # =========================================================================
    def _mostrar_painel_principal(self):
        self._limpar_container()
        PainelPrincipal(
            self.container,
            config      = self.config,
            on_log      = self._add_log,
            on_status   = self._set_topbar_status,
        )

    def _limpar_container(self):
        for w in self.container.winfo_children():
            w.destroy()

    # =========================================================================
    # CALLBACKS GLOBAIS
    # =========================================================================
    def _add_log(self, msg: str):
        pass  

    def _set_topbar_status(self, status: str):
        cores = {
            "MINERANDO": COR["green"],
            "PAUSADO"  : COR["amber"],
            "PARADO"   : COR["red"],
            "BOOT"     : COR["text2"],
        }
        cor  = cores.get(status, COR["text2"])
        icon = "●" if status == "MINERANDO" else "○"
        self.lbl_topbar_status.config(
            text=f"{icon} {status}", fg=cor
        )

    def _on_close(self):
        if messagebox.askyesno(
            "Sair",
            "Encerrar o minerador?\n\nA mineração será pausada.",
            icon="warning"
        ):
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# =============================================================================
# TELA DE BOOT — Primeiro uso
# =============================================================================
class BootScreen(tk.Frame):

    FASES = [
        ("Detectando processador...",    0.6),
        ("Lendo memória RAM...",         0.5),
        ("Verificando GPU...",           0.9),
        ("Calculando score...",          0.4),
        ("Classificando nó...",          0.3),
        ("Gerando node_id (BLAKE3)...",  0.3),
        ("Preparando vínculo...",        0.5),
    ]

    def __init__(self, parent, callback):
        super().__init__(parent, bg=COR["bg"])
        self.pack(fill="both", expand=True)
        self.callback = callback
        self._hw      = None
        self._result  = None

        self._build()
        self._iniciar_deteccao()

    def _build(self):
        spacer = tk.Frame(self, bg=COR["bg"], height=30)
        spacer.pack()

        frames, delays = _carregar_gif(LOGO_PATH, altura=80)
        if frames:
            lbl_logo = tk.Label(self, bg=COR["bg"], bd=0, highlightthickness=0)
            lbl_logo.pack(pady=(0, 6))
            _animar_label_gif(lbl_logo, frames, delays)
        else:
            tk.Label(self, text="⬡",
                     font=("Courier New", 48, "bold"),
                     bg=COR["bg"], fg=COR["cyan"]).pack()

        tk.Label(self, text="PLEGMA MINERADOR",
                 font=("Courier New", 18, "bold"),
                 bg=COR["bg"], fg=COR["cyan"]).pack()
        tk.Label(self, text="Analisando hardware do sistema...",
                 font=FONTE_MONO, bg=COR["bg"], fg=COR["text2"]).pack(pady=(4, 20))

        frame_prog = tk.Frame(self, bg=COR["bg"], width=480)
        frame_prog.pack()

        self.lbl_fase = tk.Label(
            frame_prog, text="Iniciando...",
            font=FONTE_MONO2, bg=COR["bg"], fg=COR["text2"], width=40
        )
        self.lbl_fase.pack(pady=(0, 6))

        self.canvas_prog = tk.Canvas(
            frame_prog, width=460, height=6,
            bg=COR["border"], highlightthickness=0
        )
        self.canvas_prog.pack()
        self.barra_fill = self.canvas_prog.create_rectangle(
            0, 0, 0, 6, fill=COR["cyan"], outline=""
        )

        self.lbl_pct = tk.Label(
            frame_prog, text="0%",
            font=FONTE_MONO2, bg=COR["bg"], fg=COR["cyan"]
        )
        self.lbl_pct.pack(pady=(4, 20))

        self.frame_resultado = tk.Frame(self, bg=COR["bg"])
        self.frame_resultado.pack(fill="x", padx=60)

    def _iniciar_deteccao(self):
        def run():
            hw = detectar_hardware()
            self._hw = hw
            self._result = classificar(hw)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self._animar_fase(0, t)

    def _animar_fase(self, idx: int, thread: threading.Thread):
        total = len(self.FASES)

        if idx < total:
            label, delay = self.FASES[idx]
            self.lbl_fase.config(text=label)
            pct = int((idx / total) * 100)
            self.lbl_pct.config(text=f"{pct}%")
            self.canvas_prog.coords(
                self.barra_fill, 0, 0, int(460 * idx / total), 6
            )
            self.after(int(delay * 1000), lambda: self._animar_fase(idx + 1, thread))
        else:
            self.after(200, lambda: self._verificar_thread(thread))

    def _verificar_thread(self, thread: threading.Thread):
        if thread.is_alive():
            self.after(100, lambda: self._verificar_thread(thread))
        else:
            self._mostrar_resultado()

    def _mostrar_resultado(self):
        self.lbl_fase.config(text="Análise concluída ✓")
        self.lbl_pct.config(text="100%")
        self.canvas_prog.coords(self.barra_fill, 0, 0, 460, 6)

        hw  = self._hw
        res = self._result

        cor_tipo = COR["amber"] if res["tipo"] == "PROVER" else COR["cyan"]

        for w in self.frame_resultado.winfo_children():
            w.destroy()

        card = tk.Frame(
            self.frame_resultado,
            bg=COR["bg2"], padx=20, pady=16,
        )
        card.pack(fill="x", pady=10)

        tk.Frame(card, bg=cor_tipo, height=2).pack(fill="x", pady=(0, 12))

        linha1 = tk.Frame(card, bg=COR["bg2"])
        linha1.pack(fill="x")

        tk.Label(
            linha1, text=res["tipo"],
            font=("Courier New", 18, "bold"),
            bg=COR["bg2"], fg=cor_tipo
        ).pack(side="left")

        tk.Label(
            linha1, text=f"Score: {res['score']}",
            font=FONTE_MONO, bg=COR["bg2"], fg=COR["text2"]
        ).pack(side="right")

        tk.Label(
            card, text=res["descricao"],
            font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
        ).pack(anchor="w", pady=(4, 10))

        specs = tk.Frame(card, bg=COR["bg2"])
        specs.pack(fill="x")

        def spec_row(label, value, cor=None):
            f = tk.Frame(specs, bg=COR["bg2"])
            f.pack(fill="x", pady=1)
            tk.Label(f, text=label, font=FONTE_MONO2,
                     bg=COR["bg2"], fg=COR["text2"], width=18, anchor="w").pack(side="left")
            tk.Label(f, text=value, font=FONTE_MONO2,
                     bg=COR["bg2"], fg=cor or COR["text"]).pack(side="left")

        spec_row("CPU:",        f"{hw['cpu_model'][:40]}")
        spec_row("Núcleos:",    f"{hw['cpu_cores_fisicos']} físicos / {hw['cpu_cores_logicos']} lógicos")
        spec_row("RAM:",        f"{hw['ram_total_gb']} GB")
        spec_row("GPU:",        hw['gpu_nome'] + (f" ({hw['gpu_vram_gb']} GB)" if hw['has_gpu'] else ""),
                 cor=COR["cyan"] if hw['has_gpu'] else COR["text2"])
        spec_row("Node ID:",    res["node_id"], cor=COR["cyan"])
        spec_row("Pool:",       f"{'Prover 40%' if res['tipo'] == 'PROVER' else 'Validator 60%'}",
                 cor=cor_tipo)

        tk.Frame(card, bg=cor_tipo, height=1).pack(fill="x", pady=(12, 0))

        tk.Frame(self.frame_resultado, bg=COR["bg"], height=10).pack()
        tk.Label(
            self.frame_resultado,
            text="Endereço PLG do celular dono (todas as recompensas vão para este endereço):",
            font=FONTE_MONO2, bg=COR["bg"], fg=COR["text2"]
        ).pack(anchor="w")

        frame_plg = tk.Frame(self.frame_resultado, bg=COR["bg"])
        frame_plg.pack(fill="x", pady=(4, 12))

        self.entry_plg = tk.Entry(
            frame_plg,
            font=FONTE_MONO2, bg=COR["bg3"], fg=COR["cyan"],
            insertbackground=COR["cyan"],
            relief="flat", bd=0,
        )
        self.entry_plg.pack(side="left", fill="x", expand=True,
                            ipady=8, padx=(0, 8))

        lbl_err = tk.Label(
            self.frame_resultado, text="",
            font=FONTE_MONO2, bg=COR["bg"], fg=COR["red"]
        )
        lbl_err.pack(anchor="w")

        def confirmar():
            plg = self.entry_plg.get().strip().upper()
            if not (plg.startswith("PLG") and len(plg) == 43):
                lbl_err.config(text="Endereço inválido. Deve iniciar com PLG e ter 43 caracteres.")
                return
            lbl_err.config(text="")

            cfg = {
                "plg_address" : plg,
                "node_id"     : res["node_id"],
                "node_type"   : res["tipo"],
                "score"       : res["score"],
                "categoria"   : res["categoria"],
                "cpu"         : hw["cpu_model"][:40],
                "cpu_cores"   : hw["cpu_cores_fisicos"],
                "ram_gb"      : hw["ram_total_gb"],
                "gpu"         : hw["gpu_nome"],
                "gpu_vram"    : hw["gpu_vram_gb"],
                "configurado_em": datetime.now().isoformat()
            }
            self.callback(cfg)

        btn = tk.Button(
            frame_plg,
            text="CONFIRMAR →",
            font=("Courier New", 9, "bold"),
            bg=COR["cyan"], fg="#000",
            activebackground="#00d4e0", activeforeground="#000",
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=confirmar
        )
        btn.pack(side="right")


# =============================================================================
# PAINEL PRINCIPAL — Dashboard do Minerador
# =============================================================================
class PainelPrincipal(tk.Frame):

    def __init__(self, parent, config, on_log, on_status):
        super().__init__(parent, bg=COR["bg"])
        self.pack(fill="both", expand=True)

        self.config     = config
        self.on_log_ext = on_log
        self.on_status  = on_status
        self.engine     = None
        self._server    = None

        self._build()
        self._iniciar_engine()

    def _build(self):
        self.sidebar  = tk.Frame(self, bg=COR["bg2"], width=200)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        sep = tk.Frame(self, bg=COR["border"], width=1)
        sep.pack(side="left", fill="y")

        self.content  = tk.Frame(self, bg=COR["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_content()

    def _build_sidebar(self):
        sb = self.sidebar

        brand = tk.Frame(sb, bg=COR["bg2"])
        brand.pack(fill="x", padx=10, pady=(12, 4))

        frames, delays = _carregar_gif(LOGO_PATH, altura=28)
        if frames:
            lbl_logo = tk.Label(brand, bg=COR["bg2"], bd=0, highlightthickness=0)
            lbl_logo.pack(side="left", padx=(4, 6))
            _animar_label_gif(lbl_logo, frames, delays)
        else:
            tk.Label(brand, text="⬡", font=("Courier New", 18, "bold"),
                     bg=COR["bg2"], fg=COR["cyan"]).pack(side="left", padx=(4, 6))

        tk.Label(brand, text="PLEGMA DAG",
                 font=("Courier New", 9, "bold"),
                 bg=COR["bg2"], fg=COR["cyan"]).pack(side="left")

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=10, pady=(6, 10))

        tk.Label(sb, text="NÓ ATUAL", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")

        cor_tipo = COR["amber"] if self.config.get("node_type") == "PROVER" else COR["cyan"]
        tk.Label(sb, text=self.config.get("node_type", "--"),
                 font=("Courier New", 14, "bold"),
                 bg=COR["bg2"], fg=cor_tipo).pack(padx=14, anchor="w")

        tk.Label(sb,
                 text=self.config.get("node_id", "--")[:18],
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
                 ).pack(padx=14, anchor="w", pady=(2, 0))

        tk.Label(sb,
                 text=f"Score: {self.config.get('score', '--')}",
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
                 ).pack(padx=14, anchor="w")

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=14, pady=10)

        plg = self.config.get("plg_address", "")
        tk.Label(sb, text="DONO PLG", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")
        tk.Label(sb, text=plg[:8]+"..."+plg[-4:] if len(plg) > 12 else plg,
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["cyan"]
                 ).pack(padx=14, anchor="w")

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=14, pady=10)

        tk.Label(sb, text="CONTROLE", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")

        self.btn_toggle = tk.Button(
            sb, text="⏸ PAUSAR",
            font=("Courier New", 9, "bold"),
            bg=COR["amber"], fg="#000",
            activebackground="#d97706", activeforeground="#000",
            relief="flat", cursor="hand2",
            command=self._toggle_mineracao
        )
        self.btn_toggle.pack(fill="x", padx=14, pady=(6, 4))

        tk.Button(
            sb, text="⟳ REINICIAR",
            font=FONTE_MONO2,
            bg=COR["bg3"], fg=COR["text"],
            activebackground=COR["border"], activeforeground=COR["text"],
            relief="flat", cursor="hand2",
            command=self._reiniciar
        ).pack(fill="x", padx=14, pady=2)

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=14, pady=10)

        pool_label = "Prover (40%)" if self.config.get("node_type") == "PROVER" else "Validator (60%)"
        tk.Label(sb, text="POOL", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")
        tk.Label(sb, text=pool_label, font=FONTE_MONO2,
                 bg=COR["bg2"], fg=cor_tipo).pack(padx=14, anchor="w")

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=14, pady=10)
        tk.Label(sb, text="DAG STATUS", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")
        self.lbl_dag_status = tk.Label(sb, text="● CONECTANDO...",
                                        font=FONTE_MONO2,
                                        bg=COR["bg2"], fg=COR["amber"])
        self.lbl_dag_status.pack(padx=14, anchor="w")

        tk.Frame(sb, bg=COR["border"], height=1).pack(fill="x", padx=14, pady=10)
        tk.Label(sb, text="API LOCAL :8084", font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(padx=14, anchor="w")
        tk.Label(sb, text="● ATIVO",
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["green"]
                 ).pack(padx=14, anchor="w")

    def _build_content(self):
        ct = self.content

        tk.Frame(ct, bg=COR["bg"], height=16).pack()

        row1 = tk.Frame(ct, bg=COR["bg"])
        row1.pack(fill="x", padx=16)

        self._card_metrica(row1, "HASHRATE",         "0.00 H/s",    "hashrate",    COR["cyan"])
        self._card_metrica(row1, "TOTAL MINERADO",   "0.0000 $PLG", "recompensa",  COR["green"])
        self._card_metrica(row1, "VÉRTICES ACEITOS", "0",           "aceitas",     COR["cyan"])
        self._card_metrica(row1, "UPTIME",           "00:00:00",    "uptime",      COR["amber"])

        row2 = tk.Frame(ct, bg=COR["bg"])
        row2.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        frame_log = tk.Frame(row2, bg=COR["bg2"], padx=0, pady=0)
        frame_log.pack(side="left", fill="both", expand=True)

        tk.Frame(frame_log, bg=COR["cyan"], height=2).pack(fill="x")
        tk.Label(frame_log, text="LOG DE MINERAÇÃO",
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
                 ).pack(anchor="w", padx=10, pady=(6, 4))

        self.txt_log = tk.Text(
            frame_log,
            font=FONTE_MONO2,
            bg=COR["bg2"], fg=COR["text"],
            insertbackground=COR["cyan"],
            relief="flat", state="disabled",
            wrap="word", height=14,
        )
        self.txt_log.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        self.txt_log.tag_config("ok",   foreground=COR["green"])
        self.txt_log.tag_config("warn", foreground=COR["amber"])
        self.txt_log.tag_config("err",  foreground=COR["red"])
        self.txt_log.tag_config("info", foreground=COR["text2"])
        self.txt_log.tag_config("cyan", foreground=COR["cyan"])

        col_r = tk.Frame(row2, bg=COR["bg"], width=210)
        col_r.pack(side="right", fill="y", padx=(10, 0))
        col_r.pack_propagate(False)

        self._build_stats_panel(col_r)

        tk.Frame(ct, bg=COR["border"], height=1).pack(fill="x", padx=16, pady=(8, 0))
        footer = tk.Frame(ct, bg=COR["bg"])
        footer.pack(fill="x", padx=16, pady=4)
        tk.Label(footer,
                 text="© 2026 PLEGMA DAG | THE ARCHITECTURE OF ABSOLUTE JUSTICE",
                 font=FONTE_MONO2, bg=COR["bg"], fg=COR["text2"]
                 ).pack()

    def _card_metrica(self, parent, label, valor_inicial, key, cor):
        card = tk.Frame(parent, bg=COR["bg2"], padx=12, pady=10)
        card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Frame(card, bg=cor, height=2).pack(fill="x", pady=(0, 8))

        tk.Label(card, text=label, font=FONTE_MONO2,
                 bg=COR["bg2"], fg=COR["text2"]).pack(anchor="w")

        lbl = tk.Label(card, text=valor_inicial,
                       font=("Courier New", 13, "bold"),
                       bg=COR["bg2"], fg=cor)
        lbl.pack(anchor="w", pady=(4, 0))

        setattr(self, f"lbl_{key}", lbl)

    def _build_stats_panel(self, parent):
        tk.Frame(parent, bg=COR["amber"], height=2).pack(fill="x")

        tk.Label(parent, text="ESTATÍSTICAS",
                 font=FONTE_MONO2, bg=COR["bg2"], fg=COR["text2"]
                 ).pack(anchor="w", padx=10, pady=(6, 8))

        self._stat_rows = {}

        def stat(label, valor_id, cor=None):
            f = tk.Frame(parent, bg=COR["bg2"])
            f.pack(fill="x", padx=10, pady=2)
            tk.Label(f, text=label, font=FONTE_MONO2,
                     bg=COR["bg2"], fg=COR["text2"],
                     width=12, anchor="w").pack(side="left")
            lbl = tk.Label(f, text="--", font=FONTE_MONO2,
                           bg=COR["bg2"], fg=cor or COR["text"])
            lbl.pack(side="right")
            self._stat_rows[valor_id] = lbl

        stat("Rejeitadas",  "rejeitadas", COR["red"])
        stat("Nós Ativos",  "nos",        COR["cyan"])
        stat("Última TX",   "ultima",     COR["green"])
        stat("CPU",         "cpu",        COR["text"])
        stat("RAM",         "ram",        COR["text"])
        stat("GPU",         "gpu",        COR["cyan"])
        stat("Score",       "score",      COR["amber"])
        stat("Pool",        "pool",       COR["amber"])

        self._stat_rows["cpu"].config(
            text=self.config.get("cpu", "--")[:14]
        )
        self._stat_rows["ram"].config(
            text=f"{self.config.get('ram_gb', '--')} GB"
        )
        self._stat_rows["gpu"].config(
            text=(self.config.get("gpu", "N/A")[:14])
        )
        self._stat_rows["score"].config(
            text=str(self.config.get("score", "--"))
        )
        pool = "Prover 40%" if self.config.get("node_type") == "PROVER" else "Validator 60%"
        self._stat_rows["pool"].config(text=pool)

    def _iniciar_engine(self):
        self.engine = MinerEngine(
            plg_address = self.config["plg_address"],
            node_id     = self.config["node_id"],
            node_type   = self.config["node_type"],
            on_log      = self._add_log,
            on_stats    = self._atualizar_stats,
            on_status   = self._atualizar_status_topbar,
        )
        try:
            self._server = iniciar_servidor(self.engine, porta=8084)
        except Exception:
            pass

        self.engine.iniciar()
        self.btn_toggle.config(text="⏸ PAUSAR")
        self._add_log(
            f"Minerador iniciado como {self.config['node_type']} "
            f"(Score: {self.config['score']})", "cyan"
        )

    def _toggle_mineracao(self):
        if not self.engine:
            return
        if self.engine.pausado:
            self.engine.retomar()
            self.btn_toggle.config(text="⏸ PAUSAR", bg=COR["amber"])
        else:
            self.engine.pausar()
            self.btn_toggle.config(text="▶ RETOMAR", bg=COR["green"])

    def _reiniciar(self):
        if self.engine:
            self.engine.parar()
            self.after(500, self._iniciar_engine)

    def _add_log(self, msg: str, tag: str = "info"):
        def _inserir():
            self.txt_log.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            linha = f"[{ts}] {msg}\n"
            self.txt_log.insert("end", linha, tag)
            self.txt_log.see("end")
            linhas = int(self.txt_log.index("end-1c").split(".")[0])
            if linhas > LOG_MAX:
                self.txt_log.delete("1.0", "2.0")
            self.txt_log.config(state="disabled")

        self.after(0, _inserir)

    def _atualizar_stats(self, stats: dict):
        def _update():
            hr = stats.get("hashrate", 0)
            self.lbl_hashrate.config(
                text=f"{hr:.2f} H/s"
            )
            self.lbl_recompensa.config(
                text=formatar_plg(stats.get("total_recompensa", 0))
            )
            self.lbl_aceitas.config(
                text=str(stats.get("total_aceitas", 0))
            )

            s = stats.get("uptime_segundos", 0)
            h, r = divmod(s, 3600)
            m, sc= divmod(r, 60)
            self.lbl_uptime.config(text=f"{h:02d}:{m:02d}:{sc:02d}")

            self._stat_rows["rejeitadas"].config(
                text=str(stats.get("total_rejeitadas", 0))
            )
            self._stat_rows["nos"].config(
                text=str(stats.get("nos_ativos", "--"))
            )
            self._stat_rows["ultima"].config(
                text=stats.get("ultima_tx", "--")
            )

            dag = stats.get("dag_status", "--")
            cor = COR["green"] if dag == "ONLINE" else (
                  COR["amber"] if dag == "SIMULAÇÃO" else COR["red"])
            self.lbl_dag_status.config(
                text=f"● {dag}", fg=cor
            )

        self.after(0, _update)

    def _atualizar_status_topbar(self, status: str):
        self.after(0, lambda: self.on_status(status))


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 50)
    print(" [PLEGMA] MINERADOR V4.0")
    print("=" * 50)
    print(" Dependencias: pip install psutil qrcode pillow")
    print(" Iniciando interface grafica Pos-Quantica...")
    print()

    app = MineradorGUI()
    app.run()