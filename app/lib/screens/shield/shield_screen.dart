import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../theme/plegma_theme.dart';
import '../../services/auth_service.dart';
import '../../services/storage_service.dart';
import '../../services/crypto_service.dart';
import '../../services/dilithium_ffi_service.dart';
import '../../services/api_service.dart';
import '../../services/deep_link_service.dart';
import '../../services/snapshot_service.dart';
import '../../widgets/plegma_card.dart';
import '../auth/recover_account_screen.dart';

// MethodChannel para acesso ao PackageManager do Android
const _kShieldChannel = MethodChannel('com.plegmadag.app/shield');

// ─────────────────────────────────────────────────────────────────────────────
// ShieldScreen — gatekeeper: mostra ativação ou as 3 abas funcionais
// ─────────────────────────────────────────────────────────────────────────────

class ShieldScreen extends StatefulWidget {
  const ShieldScreen({super.key});
  @override
  State<ShieldScreen> createState() => _ShieldScreenState();
}

class _ShieldScreenState extends State<ShieldScreen> {
  bool _shieldAtivo = false;
  bool _carregando  = true;

  @override
  void initState() {
    super.initState();
    _carregarEstado();
  }

  Future<void> _carregarEstado() async {
    // Lê estado local primeiro (rápido)
    final local = await StorageService.shieldAtivoLer();
    if (local) {
      if (mounted) setState(() { _shieldAtivo = true; _carregando = false; });
      _verificarBackend(); // confirmação assíncrona em background
      return;
    }
    // Consulta backend — endereço pode já ter assinatura ativa (reinstalação)
    final addr = await StorageService.lerEndereco() ?? '';
    if (addr.isNotEmpty) {
      final sub = await ApiService.shieldGetSubscription(addr);
      if (sub != null && sub['ativo'] == true) {
        await StorageService.shieldAtivoSalvar(true);
        if (mounted) setState(() { _shieldAtivo = true; _carregando = false; });
        return;
      }
    }
    if (mounted) setState(() { _shieldAtivo = false; _carregando = false; });
  }

  Future<void> _verificarBackend() async {
    final addr = await StorageService.lerEndereco() ?? '';
    if (addr.isEmpty) return;
    final sub = await ApiService.shieldGetSubscription(addr);
    // Só desactiva se o servidor responder explicitamente com ativo:false.
    // null = falha de rede → manter estado local (não revogar subscrição por timeout).
    if (sub != null && sub['ativo'] == false) {
      await StorageService.shieldAtivoSalvar(false);
      if (mounted) setState(() => _shieldAtivo = false);
    }
  }

  Future<void> _desativar() async {
    final addr = await StorageService.lerEndereco() ?? '';
    await ApiService.shieldUnsubscribe(addr);
    await StorageService.shieldAtivoSalvar(false);
    if (mounted) setState(() => _shieldAtivo = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_carregando && !kIsWeb) {
      return const Scaffold(
        backgroundColor: PlegmaColors.bg,
        body: Center(child: CircularProgressIndicator(color: PlegmaColors.cyan)),
      );
    }
    final ativo = kIsWeb ? true : _shieldAtivo;
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        backgroundColor: PlegmaColors.bg,
        appBar: AppBar(
          title: const Text('LATTICE SHIELD', style: TextStyle(letterSpacing: 3)),
          actions: [
            if (ativo && !kIsWeb)
              TextButton(
                onPressed: _desativar,
                child: const Text('DESATIVAR',
                    style: TextStyle(color: PlegmaColors.red, fontSize: 10, letterSpacing: 1)),
              ),
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: StatusBadge(
                label: ativo ? 'ATIVO' : 'INATIVO',
                color: ativo ? PlegmaColors.green : PlegmaColors.red,
              ),
            ),
          ],
          bottom: const TabBar(
            indicatorColor: PlegmaColors.cyan,
            labelColor: PlegmaColors.cyan,
            unselectedLabelColor: PlegmaColors.textDim,
            labelStyle: TextStyle(fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold),
            tabs: [
              Tab(text: 'AUTENTICAR'),
              Tab(text: 'SCANNER'),
              Tab(text: 'PERMISSÕES'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _AuthTab(shieldAtivo: ativo, onAtivado: kIsWeb ? null : _carregarEstado),
            _ScannerTab(shieldAtivo: ativo),
            _PermissoesTab(shieldAtivo: ativo),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// View de Ativação — fluxo de compra seguindo padrão Shield Usuário do Dashboard
// ─────────────────────────────────────────────────────────────────────────────

class _ShieldAtivacaoView extends StatefulWidget {
  final VoidCallback onAtivado;
  const _ShieldAtivacaoView({required this.onAtivado});
  @override
  State<_ShieldAtivacaoView> createState() => _ShieldAtivacaoViewState();
}

class _ShieldAtivacaoViewState extends State<_ShieldAtivacaoView> {
  bool   _termoAceito    = false;
  bool   _ativando       = false;
  bool   _carregandoInfo = true;
  String _metodoPagamento = '';         // "gratis_genesis" | "carteira" | "mineracao"
  Map<String, dynamic>? _payInfo;       // resposta de /shield/payment/check

  @override
  void initState() {
    super.initState();
    _carregarInfoPagamento();
  }

  Future<void> _carregarInfoPagamento() async {
    final addr = await StorageService.lerEndereco() ?? '';
    final info = addr.isNotEmpty ? await ApiService.shieldPaymentCheck(addr) : null;
    if (!mounted) return;

    // Período gratuito local: antes de 09 Jun 2026 → forçar genesis_ativo independente do servidor
    final genesisLocalAtivo = DateTime.now().isBefore(DateTime.utc(2026, 6, 9));
    Map<String, dynamic>? payInfo;
    if (genesisLocalAtivo) {
      payInfo = Map<String, dynamic>.from(info ?? {});
      payInfo['genesis_ativo'] = true;
    } else {
      payInfo = info;
    }

    setState(() {
      _payInfo        = payInfo;
      _carregandoInfo = false;
      // Pré-seleciona: genesis > mineração > carteira
      if (payInfo?['genesis_ativo'] == true)     _metodoPagamento = 'gratis_genesis';
      else if (payInfo?['eh_validador'] == true)  _metodoPagamento = 'mineracao';
      else                                         _metodoPagamento = 'carteira';
    });
  }

  Future<void> _ativar() async {
    if (!_termoAceito || _ativando || _metodoPagamento.isEmpty) return;

    // Bloqueia se carteira sem saldo suficiente
    if (_metodoPagamento == 'carteira' &&
        _payInfo?['saldo_suficiente'] != true &&
        _payInfo?['eh_validador'] != true) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Ative o validador ou adquira PLG para continuar.'),
          backgroundColor: PlegmaColors.red,
          duration: Duration(seconds: 3),
        ),
      );
      return;
    }

    // Quando método=carteira com saldo: exibe modal de confirmação antes de debitar
    if (_metodoPagamento == 'carteira') {
      final addr     = await StorageService.lerEndereco() ?? '';
      final treasury = _payInfo?['treasury_address'] as String? ?? 'PLG_SHIELD_TREASURY_000000000000000000000000';
      final preco    = (_payInfo?['preco_plg'] as num?)?.toDouble() ?? 1200.0;
      final serviceId = 'SHIELD_SUB_${addr.length > 8 ? addr.substring(addr.length - 8) : addr}';

      final confirmed = await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        backgroundColor: PlegmaColors.bg2,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        builder: (_) => Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom + 24,
            left: 20, right: 20, top: 8,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 36, height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: PlegmaColors.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const Text('CONFIRMAR PAGAMENTO PLG',
                style: TextStyle(fontSize: 13, color: PlegmaColors.cyan,
                    letterSpacing: 2, fontWeight: FontWeight.bold)),
              const SizedBox(height: 16),
              _infoRowPag('Destinatário', treasury, PlegmaColors.textDim),
              const SizedBox(height: 10),
              _infoRowPag('Valor', '${preco.toStringAsFixed(0)} PLG  ≈  US\$ 12,00', PlegmaColors.cyan),
              const SizedBox(height: 10),
              _infoRowPag('Identificador de Serviço', serviceId, PlegmaColors.amber),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: PlegmaColors.amber.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: PlegmaColors.amber.withValues(alpha: 0.25)),
                ),
                child: const Text(
                  'O valor será debitado da sua carteira PLG e enviado ao '
                  'Aerarium, que gerencia a distribuição conforme o protocolo.',
                  style: TextStyle(fontSize: 10, color: PlegmaColors.textDim, height: 1.5),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  child: const Text('CONFIRMAR E ATIVAR',
                    style: TextStyle(fontSize: 13, letterSpacing: 2, fontWeight: FontWeight.bold)),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('CANCELAR',
                    style: TextStyle(color: PlegmaColors.textDim, letterSpacing: 1)),
                ),
              ),
            ],
          ),
        ),
      );
      if (confirmed != true) return;
    }

    setState(() => _ativando = true);
    final work = _executarAtivacao();

    final ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.black,
      builder: (_) => _ActivationOverlay(workFuture: work),
    ) ?? false;

    if (!mounted) return;
    setState(() => _ativando = false);
    if (ok) widget.onAtivado();
  }

  Widget _infoRowPag(String label, String value, Color valueColor) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5)),
      const SizedBox(height: 3),
      Text(value, style: TextStyle(fontSize: 11, color: valueColor, fontWeight: FontWeight.bold),
          maxLines: 2, overflow: TextOverflow.ellipsis),
    ],
  );

  Future<void> _executarAtivacao() async {
    final addr    = await StorageService.lerEndereco() ?? '';
    String txId   = '';

    if (_metodoPagamento == 'carteira') {
      // Assina e transfere PLG para o treasury
      final preco   = (_payInfo?['preco_plg'] as num?)?.toDouble() ?? 1200.0;
      final treasury = _payInfo?['treasury_address'] as String? ?? '';
      final privKey  = await StorageService.lerChavePrivada() ?? '';
      final sig      = await CryptoService.assinarNonce('shield:$addr:$preco', privKey);
      final tx = await ApiService.transferirPlg(
        de: addr, para: treasury, amount: preco, assinatura: sig,
      );
      txId = tx?['tx_id'] as String? ?? tx?['hash'] as String? ?? '';
    }

    final resp = await ApiService.shieldSubscribe(addr, metodo: _metodoPagamento, txId: txId);
    if (resp == null) throw Exception('Servidor Shield indisponível');
    if (resp.containsKey('http_status')) {
      final errCode = resp['error'] as String? ?? '';
      if (errCode == 'fase_genesis_encerrada') {
        // Genesis ainda não iniciou ou já encerrou — abrir página genesis no browser
        await launchUrl(
          Uri.parse('https://plegmadag.com/genesis/'),
          mode: LaunchMode.externalApplication,
        );
        throw Exception('Abra a Fase Genesis no Dashboard para ativar gratuitamente.');
      }
      throw Exception(errCode.isNotEmpty ? errCode : 'Falha na ativação');
    }
    await StorageService.shieldAtivoSalvar(true);
    SnapshotService.criarSnapshot(addr).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [

        // ── Hero ──
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color       : PlegmaColors.bg2,
            borderRadius: BorderRadius.circular(16),
            border      : Border.all(color: PlegmaColors.cyanBord),
          ),
          child: Column(
            children: [
              const Icon(Icons.security, size: 60, color: PlegmaColors.cyan),
              const SizedBox(height: 12),
              const Text('LATTICE SHIELD',
                  style: TextStyle(fontSize: 18, color: PlegmaColors.cyan,
                      letterSpacing: 3, fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              const Text('Proteção Pós-Quântica do Dispositivo',
                  style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
              const SizedBox(height: 18),
              // ── Seletor de método de pagamento ──
              if (_carregandoInfo)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: PlegmaColors.cyan),
                  ),
                )
              else
                _PaymentSelector(
                  payInfo        : _payInfo,
                  metodoSelecionado: _metodoPagamento,
                  onChanged      : (m) => setState(() => _metodoPagamento = m),
                ),
            ],
          ),
        ),

        const SizedBox(height: 14),

        // ── O que protege ──
        PlegmaCard(
          topAccent: PlegmaColors.cyan,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PlegmaLabel('O que este plano protege'),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount  : 2,
                shrinkWrap      : true,
                physics         : const NeverScrollableScrollPhysics(),
                mainAxisSpacing : 8,
                crossAxisSpacing: 8,
                childAspectRatio: 3.2,
                children: [
                  _protCard(Icons.bug_report_outlined,          'Scanner de Malware'),
                  _protCard(Icons.phishing_outlined,            'Anti-Phishing'),
                  _protCard(Icons.verified_user_outlined,       'Integridade ZK'),
                  _protCard(Icons.admin_panel_settings_outlined,'Monitor Permissões'),
                  _protCard(Icons.fingerprint,                  'Auth Dilithium3'),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 10),

        // ── Funcionalidades ──
        PlegmaCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PlegmaLabel('Funcionalidades'),
              const SizedBox(height: 10),
              _featRow('✅', 'Scanner de apps em tempo real'),
              _featRow('✅', 'Verificador de URLs anti-phishing'),
              _featRow('✅', 'Snapshot ZK do estado do dispositivo'),
              _featRow('✅', 'Monitor de permissões sensíveis'),
              _featRow('✅', 'Autenticação QR Dilithium3'),
              _featRow('✅', 'Alertas de mudança de apps instalados'),
              _featRow('🔒', 'PIN de Pânico (V2.0+)'),
              _featRow('🔒', 'Pacto dos 5 Nós (V2.0+)'),
              _featRow('🔒', 'Tela Fantasma (V2.0+)'),
            ],
          ),
        ),

        const SizedBox(height: 10),

        // ── Modelo de cobrança ──
        PlegmaCard(
          borderColor: PlegmaColors.amber.withValues(alpha: 0.35),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              PlegmaLabel('Modelo de Cobrança', color: PlegmaColors.amber),
              SizedBox(height: 10),
              Text(
                '• Validadores — Desconto direto da mineração\n'
                '  US\$ 12 / Ano com débito direto em PLG\n'
                '• GRÁTIS durante os 30 dias da Fase Genesis',
                style: TextStyle(
                    fontSize: 12, color: PlegmaColors.textDim, height: 1.7),
              ),
            ],
          ),
        ),

        const SizedBox(height: 10),

        // ── Termo de contratação ──
        PlegmaCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PlegmaLabel('Termo de Contratação'),
              const SizedBox(height: 10),
              Container(
                height: 130,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color       : PlegmaColors.bg,
                  borderRadius: BorderRadius.circular(6),
                  border      : Border.all(color: PlegmaColors.border),
                ),
                child: const SingleChildScrollView(
                  child: Text(
                    'Ao ativar o Lattice Shield, o usuário consente que o PLEGMA '
                    'leia a lista de aplicativos instalados no dispositivo UMA ÚNICA VEZ, '
                    'exclusivamente para computar um hash criptográfico de estado (SHA3-256). '
                    'Nenhuma lista de apps é transmitida para os servidores PLEGMA. '
                    'Apenas o hash (prova ZK) é ancorado na rede DAG.\n\n'
                    'O monitoramento contínuo é realizado LOCALMENTE via BroadcastReceiver '
                    'Android, sem consumo de dados de rede. Qualquer mudança no estado dos '
                    'apps é detectada e notificada ao usuário.\n\n'
                    'Este serviço é prestado na modalidade SaaS. '
                    'O cancelamento pode ser feito a qualquer momento nesta tela.',
                    style: TextStyle(
                        fontSize: 11, color: PlegmaColors.textDim, height: 1.6),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              GestureDetector(
                onTap: () => setState(() => _termoAceito = !_termoAceito),
                child: Row(
                  children: [
                    SizedBox(
                      width: 20, height: 20,
                      child: Checkbox(
                        value        : _termoAceito,
                        onChanged    : (v) => setState(() => _termoAceito = v ?? false),
                        activeColor  : PlegmaColors.cyan,
                        side         : const BorderSide(color: PlegmaColors.border),
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Expanded(
                      child: Text('Li e concordo com os termos acima',
                          style: TextStyle(fontSize: 12, color: PlegmaColors.text3)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // ── Botão ATIVAR — cor segue o status da transação ──
        Builder(builder: (_) {
          final ehValidador = _payInfo?['eh_validador']    == true;
          final saldoOk     = _payInfo?['saldo_suficiente'] == true;
          final cor = _carregandoInfo
              ? PlegmaColors.textDim
              : ehValidador
                  ? PlegmaColors.green
                  : saldoOk
                      ? PlegmaColors.amber
                      : PlegmaColors.red;

          return SizedBox(
            width : double.infinity,
            height: 52,
            child : ElevatedButton.icon(
              onPressed: (_termoAceito && !_ativando) ? _ativar : null,
              style: ElevatedButton.styleFrom(
                backgroundColor: cor.withValues(alpha: 0.15),
                foregroundColor: cor,
                side: BorderSide(color: cor.withValues(alpha: 0.6), width: 1.5),
                disabledBackgroundColor: PlegmaColors.bg2,
                disabledForegroundColor: PlegmaColors.textDim,
              ),
              icon : Icon(Icons.security, size: 20, color: cor),
              label: Text(
                'ATIVAR PROTEÇÃO',
                style: TextStyle(
                  fontSize: 13, letterSpacing: 2,
                  fontWeight: FontWeight.bold, color: cor,
                ),
              ),
            ),
          );
        }),

        const SizedBox(height: 24),
      ],
    );
  }

  Widget _protCard(IconData icon, String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
    decoration: BoxDecoration(
      color       : PlegmaColors.bg,
      borderRadius: BorderRadius.circular(6),
      border      : Border.all(color: PlegmaColors.cyanBord),
    ),
    child: Row(children: [
      Icon(icon, size: 14, color: PlegmaColors.cyan),
      const SizedBox(width: 6),
      Expanded(
        child: Text(label,
            style: const TextStyle(fontSize: 10, color: PlegmaColors.text3)),
      ),
    ]),
  );

  Widget _featRow(String emoji, String label) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(children: [
      Text(emoji, style: const TextStyle(fontSize: 13)),
      const SizedBox(width: 8),
      Expanded(child: Text(label,
          style: const TextStyle(fontSize: 12, color: PlegmaColors.textDim))),
    ]),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ABA 1 — AUTENTICAR  (funcionalidade QR + Dilithium3 existente)
// ─────────────────────────────────────────────────────────────────────────────

class _AuthTab extends StatefulWidget {
  final bool shieldAtivo;
  final VoidCallback? onAtivado;
  const _AuthTab({required this.shieldAtivo, this.onAtivado});

  @override
  State<_AuthTab> createState() => _AuthTabState();
}

class _AuthTabState extends State<_AuthTab> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  String? _address;
  String? _pubKey;
  bool    _scanQR           = false;
  bool    _autenticando     = false;
  bool    _qrProcessando    = false;
  bool    _gerandoChallenge = false;
  String  _authStatus       = '';
  String? _challengeId;
  String? _challengeData;

  final _linkController = TextEditingController();

  // Snapshot ZK
  Map<String, dynamic>? _snapshot;
  SnapshotDelta?        _delta;
  bool                  _reancorando = false;

  @override
  void initState() {
    super.initState();
    _carregar();
    DeepLinkService.pendingAuthNonce.addListener(_onDeepLinkNonce);
    WidgetsBinding.instance.addPostFrameCallback((_) => _onDeepLinkNonce());
    _carregarSnapshot();
    if (!kIsWeb) _ouvirMudancasDePacotes();
  }

  @override
  void dispose() {
    DeepLinkService.pendingAuthNonce.removeListener(_onDeepLinkNonce);
    _linkController.dispose();
    super.dispose();
  }

  void _onDeepLinkNonce() {
    final nonce = DeepLinkService.pendingAuthNonce.value;
    if (nonce != null && !_autenticando) {
      DeepLinkService.pendingAuthNonce.value = null;
      _processarQR('plegma://auth?nonce=$nonce');
    }
  }

  Future<void> _carregar() async {
    final addr = await StorageService.lerEndereco();
    final pub  = await StorageService.lerChavePublica();
    setState(() { _address = addr; _pubKey = pub; });
  }

  Future<void> _carregarSnapshot() async {
    final snap  = await StorageService.lerSnapshot();
    final delta = await StorageService.lerDeltaPendente();
    if (mounted) setState(() {
      _snapshot = snap;
      _delta    = delta != null
          ? SnapshotDelta(
              adicionados: List<String>.from(delta['adicionados'] ?? []),
              removidos  : List<String>.from(delta['removidos']   ?? []),
              alterados  : List<String>.from(delta['alterados']   ?? []),
              novoHash   : delta['novo_hash'] as String? ?? '',
            )
          : null;
    });
  }

  void _ouvirMudancasDePacotes() {
    SnapshotService.packageChangeStream.listen((event) async {
      // Pacote mudou — verifica delta em background
      final delta = await SnapshotService.verificarDelta();
      if (delta != null && delta.temMudancas) {
        // Persiste delta para exibir alerta
        await StorageService.salvarDeltaPendente({
          'adicionados': delta.adicionados,
          'removidos'  : delta.removidos,
          'alterados'  : delta.alterados,
          'novo_hash'  : delta.novoHash,
          'timestamp'  : DateTime.now().millisecondsSinceEpoch,
        });
        if (mounted) setState(() => _delta = delta);
      }
    });
  }

  Future<void> _reancorararEstado() async {
    final addr = _address ?? await StorageService.lerEndereco() ?? '';
    setState(() { _reancorando = true; });
    final result = await SnapshotService.aprovarEstado(addr);
    await _carregarSnapshot();
    setState(() { _reancorando = false; });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(result.sucesso
            ? '✓ Novo estado ancorado na rede'
            : '✗ ${result.erro}'),
      ));
    }
  }

  Future<void> _processarQR(String raw) async {
    if (_qrProcessando || _autenticando) return;
    _qrProcessando = true;
    setState(() { _scanQR = false; _autenticando = true; _authStatus = 'Lendo QR...'; });

    try {
      String? nonce;
      String? callbackUrl;
      try {
        final uri = Uri.parse(raw.replaceFirst('plegma://', 'https://plegma.local/'));
        nonce       = uri.queryParameters['nonce'];
        callbackUrl = uri.queryParameters['page_callback'];
      } catch (_) {
        final match = RegExp(r'nonce=([a-zA-Z0-9]+)').firstMatch(raw);
        nonce = match?.group(1);
      }

      if (nonce == null || nonce.isEmpty) {
        if (mounted) setState(() { _autenticando = false; _authStatus = '✗ QR inválido'; });
        return;
      }

      setState(() => _authStatus = 'Confirmando biometria...');
      AuthService.beginExternalAuth();
      final autorizado = await AuthService.authenticateBiometric(
        reason: 'Confirme sua identidade para assinar a transação PLEGMA',
      );
      if (!mounted) return;
      if (!autorizado) {
        setState(() { _autenticando = false; _authStatus = '✗ Biometria não confirmada'; });
        await Future.delayed(const Duration(seconds: 2));
        if (mounted) setState(() => _authStatus = '');
        return;
      }

      setState(() => _authStatus = 'Assinando com Dilithium3...');
      final privKey = await StorageService.lerChavePrivada() ?? '';
      final pubKey  = await StorageService.lerChavePublica() ?? '';
      final addr    = await StorageService.lerEndereco() ?? '';

      if (privKey.isEmpty || pubKey.isEmpty || addr.isEmpty) {
        if (!mounted) return;
        setState(() { _autenticando = false; _authStatus = '✗ Chaves não encontradas — use Recuperar Carteira'; });
        await Future.delayed(const Duration(seconds: 2));
        if (!mounted) return;
        setState(() => _authStatus = '');
        Navigator.push(context, MaterialPageRoute(builder: (_) => const RecoverAccountScreen()));
        return;
      }

      String sigHex;
      String pubHex;
      try {
        final sigB64 = await CryptoService.assinarNonce(nonce, privKey);
        sigHex = DilithiumFfiService.bytesToHex(base64.decode(sigB64));
        pubHex = DilithiumFfiService.bytesToHex(base64.decode(pubKey));
      } catch (_) {
        if (!mounted) return;
        setState(() { _autenticando = false; _authStatus = '✗ Erro FFI — motor criptográfico indisponível'; });
        await Future.delayed(const Duration(seconds: 3));
        if (mounted) setState(() => _authStatus = '');
        return;
      }
      if (!mounted) return;

      setState(() => _authStatus = 'Verificando no servidor...');
      final result = await ApiService.authVerify(
        nonce      : nonce,
        plgAddress : addr,
        signature  : sigHex,
        publicKey  : pubHex,
      );
      if (!mounted) return;

      final ok = result?['status'] == 'verified' || result?['status'] == 'autenticado';
      if (ok) {
        final token = result?['session_token'] as String? ?? result?['token'] as String?;
        if (token != null) await StorageService.salvarSessao(token);

        // Redirecionar browser de volta à página com sessão nos params
        if (callbackUrl != null && callbackUrl.isNotEmpty && token != null && addr.isNotEmpty) {
          final sep = callbackUrl.contains('?') ? '&' : '?';
          final redirectUri = Uri.parse(
            '$callbackUrl${sep}plg_address=${Uri.encodeComponent(addr)}&plg_token=${Uri.encodeComponent(token)}',
          );
          await launchUrl(redirectUri, mode: LaunchMode.externalApplication);
        }
      }
      final errMsg = result?['error'] as String? ?? '';
      final expirado = errMsg.toLowerCase().contains('expirado') || errMsg.toLowerCase().contains('inexistente');
      setState(() {
        _autenticando = false;
        _authStatus   = ok
            ? '✓ Autenticado com sucesso!'
            : expirado
                ? '✗ QR expirado — abra o dashboard, clique em COPIAR LINK e cole novamente.'
                : '✗ Falhou: ${errMsg.isNotEmpty ? errMsg : 'Servidor indisponível'}';
      });
      await Future.delayed(Duration(seconds: expirado ? 5 : 3));
      if (mounted) setState(() => _authStatus = '');
    } finally {
      _qrProcessando = false;
      if (mounted && _autenticando) setState(() => _autenticando = false);
    }
  }

  Future<void> _gerarChallenge() async {
    final addr = _address ?? await StorageService.lerEndereco() ?? '';
    if (addr.isEmpty) {
      setState(() => _authStatus = '✗ Endereço não configurado');
      return;
    }
    setState(() {
      _gerandoChallenge = true;
      _authStatus       = 'Gerando desafio no servidor...';
      _challengeId      = null;
      _challengeData    = null;
    });

    final data = await ApiService.getAuthChallenge(addr);
    if (!mounted) return;
    if (data != null) {
      // auth_server.py retorna: {nonce, message: "plegma://auth?nonce=XXX", expires_in, site}
      final id    = data['nonce'] ?? data['challenge_id'] ?? data['id'] ?? '';
      final cData = data['message'] ?? data['challenge_data'] ?? data['data'] ?? data['qr_payload']
                    ?? 'plegma://auth?nonce=$id';
      setState(() {
        _gerandoChallenge = false;
        _challengeId      = id.toString();
        _challengeData    = cData.toString();
        _authStatus       = 'Desafio gerado. Escaneie o QR ou use o botão abaixo.';
      });
    } else {
      setState(() {
        _gerandoChallenge = false;
        _challengeId      = null;
        _challengeData    = null;
        _authStatus       = '✗ Servidor de autenticação offline';
      });
    }
  }

  Future<void> _assinarChallenge() async {
    if (_challengeId == null) return;
    setState(() { _autenticando = true; _authStatus = 'Confirmando biometria...'; });

    AuthService.beginExternalAuth();
    final autorizado = await AuthService.authenticateBiometric(
      reason: 'Confirme sua identidade para assinar a transação PLEGMA',
    );
    if (!mounted) return;
    if (!autorizado) {
      setState(() { _autenticando = false; _authStatus = '✗ Biometria não confirmada'; });
      await Future.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      setState(() => _authStatus = '');
      return;
    }

    setState(() => _authStatus = 'Assinando com Dilithium3...');
    final privKey = await StorageService.lerChavePrivada() ?? '';
    final pubKey  = await StorageService.lerChavePublica() ?? '';
    final addr    = await StorageService.lerEndereco() ?? '';

    if (privKey.isEmpty || pubKey.isEmpty || addr.isEmpty) {
      if (!mounted) return;
      setState(() { _autenticando = false; _authStatus = '✗ Chaves não encontradas — use Recuperar Carteira'; });
      await Future.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      setState(() => _authStatus = '');
      Navigator.pushNamed(context, '/recover');
      return;
    }

    String sigHex;
    String pubHex;
    try {
      // Assina o nonce e converte Base64 → hex (formato exigido pelo backend)
      final sigB64 = await CryptoService.assinarNonce(_challengeId!, privKey);
      sigHex = DilithiumFfiService.bytesToHex(base64.decode(sigB64));
      pubHex = DilithiumFfiService.bytesToHex(base64.decode(pubKey));
    } catch (_) {
      if (!mounted) return;
      setState(() { _autenticando = false; _authStatus = '✗ Erro FFI — motor criptográfico indisponível'; });
      await Future.delayed(const Duration(seconds: 3));
      if (!mounted) return;
      setState(() => _authStatus = '');
      return;
    }
    if (!mounted) return;

    setState(() => _authStatus = 'Verificando no servidor...');
    final result = await ApiService.authVerify(
      nonce      : _challengeId!,
      plgAddress : addr,
      signature  : sigHex,
      publicKey  : pubHex,
    );
    if (!mounted) return;

    final ok = result?['status'] == 'verified';
    if (ok) {
      final token = result?['session_token'] as String?;
      if (token != null) await StorageService.salvarSessao(token);
    }
    setState(() {
      _autenticando  = false;
      _challengeId   = null;
      _challengeData = null;
      _authStatus    = ok 
          ? '✓ Autenticado com sucesso!' 
          : '✗ Falhou: ${result?['error'] ?? 'Servidor indisponível'}';
    });
    await Future.delayed(const Duration(seconds: 3));
    if (!mounted) return;
    setState(() => _authStatus = '');
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Algoritmo
            PlegmaCard(
              topAccent: PlegmaColors.cyan,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const PlegmaLabel('Algoritmo de Assinatura'),
                  const SizedBox(height: 8),
                  const Text('Crystals-Dilithium3',
                      style: TextStyle(fontSize: 18, color: PlegmaColors.cyan, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  const Text('NIST FIPS 204 · Level 3 · Resistência Pós-Quântica',
                      style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
                  const SizedBox(height: 12),
                  Row(children: [
                    _specChip('PubKey: 1952 bytes'),
                    const SizedBox(width: 8),
                    _specChip('Sig: 3293 bytes'),
                  ]),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Endereço PLG
            PlegmaCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const PlegmaLabel('Endereço PLG'),
                      GestureDetector(
                        onTap: () {
                          if (_address != null) {
                            Clipboard.setData(ClipboardData(text: _address!));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Endereço copiado')),
                            );
                          }
                        },
                        child: const Icon(Icons.copy, size: 16, color: PlegmaColors.textDim),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(_address ?? '--',
                      style: const TextStyle(fontSize: 11, color: PlegmaColors.cyan, letterSpacing: 1)),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Autenticar via QR
            PlegmaCard(
              topAccent: PlegmaColors.green,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const PlegmaLabel('Autenticar no Dashboard'),
                  const SizedBox(height: 8),
                  const Text(
                    'Gere um desafio do servidor e assine com Dilithium3, ou escaneie '
                    'o QR exibido no site. A chave privada nunca sai do dispositivo.',
                    style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
                  ),
                  const SizedBox(height: 14),
                  if (_authStatus.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _authStatus,
                        style: TextStyle(
                          fontSize: 12,
                          letterSpacing: 1,
                          color: _authStatus.startsWith('✓')
                              ? PlegmaColors.green
                              : _authStatus.startsWith('✗')
                                  ? PlegmaColors.red
                                  : PlegmaColors.amber,
                        ),
                      ),
                    ),
                  if (_challengeData != null) ...[
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: PlegmaColors.bg3,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: PlegmaColors.cyan.withValues(alpha: 0.3)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('CHALLENGE DATA',
                              style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 2)),
                          const SizedBox(height: 6),
                          Text(_challengeData!,
                              style: const TextStyle(fontSize: 10, color: PlegmaColors.cyan, letterSpacing: 0.5),
                              maxLines: 3, overflow: TextOverflow.ellipsis),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _autenticando ? null : _assinarChallenge,
                        icon: const Icon(Icons.fingerprint, size: 18),
                        label: const Text('ASSINAR E VERIFICAR'),
                      ),
                    ),
                    const SizedBox(height: 8),
                  ],
                  Row(children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: (_autenticando || _gerandoChallenge) ? null : _gerarChallenge,
                        icon: _gerandoChallenge
                            ? const SizedBox(width: 14, height: 14,
                                child: CircularProgressIndicator(strokeWidth: 2, color: PlegmaColors.cyan))
                            : const Icon(Icons.generating_tokens, size: 16),
                        label: const Text('GERAR CHALLENGE'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _autenticando ? null : () => setState(() => _scanQR = true),
                        style: OutlinedButton.styleFrom(side: const BorderSide(color: PlegmaColors.cyan)),
                        icon: const Icon(Icons.qr_code_scanner, size: 16, color: PlegmaColors.cyan),
                        label: const Text('ESCANEAR QR',
                            style: TextStyle(color: PlegmaColors.cyan)),
                      ),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  // Campo para colar link do QR do dashboard
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    decoration: BoxDecoration(
                      color       : PlegmaColors.bg3,
                      borderRadius: BorderRadius.circular(8),
                      border      : Border.all(color: PlegmaColors.border),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.link, size: 16, color: PlegmaColors.textDim),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextField(
                            controller : _linkController,
                            enabled    : !_autenticando,
                            style      : const TextStyle(fontSize: 12, color: PlegmaColors.text3),
                            decoration : const InputDecoration(
                              hintText      : 'Cole o link do QR do dashboard',
                              hintStyle     : TextStyle(fontSize: 11, color: PlegmaColors.textDim),
                              border        : InputBorder.none,
                              isDense       : true,
                              contentPadding: EdgeInsets.symmetric(vertical: 10),
                            ),
                            onSubmitted: (v) {
                              final url = v.trim();
                              if (url.isNotEmpty) { _linkController.clear(); _processarQR(url); }
                            },
                          ),
                        ),
                        IconButton(
                          icon     : const Icon(Icons.send, size: 18),
                          color    : PlegmaColors.cyan,
                          padding  : EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                          tooltip  : 'Autenticar',
                          onPressed: _autenticando ? null : () {
                            final url = _linkController.text.trim();
                            if (url.isNotEmpty) { _linkController.clear(); _processarQR(url); }
                          },
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // ── Conteúdo condicional: ativação ou proteções ──────────────
            if (widget.shieldAtivo) ...[
              // Card de Snapshot ZK
              _SnapshotCard(
                snapshot    : _snapshot,
                delta       : _delta,
                reancorando : _reancorando,
                onReancorar : _reancorararEstado,
              ),
              const SizedBox(height: 12),

              // Proteções ativas
              PlegmaCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Proteções Ativas'),
                    const SizedBox(height: 12),
                    _protRow('Assinatura de Transações',  PlegmaColors.green, 'ATIVO'),
                    _protRow('Auth QR + Biometria',       PlegmaColors.green, 'ATIVO'),
                    _protRow('Scanner de Malware',        PlegmaColors.green, 'ATIVO'),
                    _protRow('Anti-Phishing de URLs',     PlegmaColors.green, 'ATIVO'),
                    _protRow('Monitor de Permissões',     PlegmaColors.green, 'ATIVO'),
                    _protRow('PIN de Pânico',             PlegmaColors.amber, 'V2.0+'),
                    _protRow('Pacto dos 5 Nós',           PlegmaColors.amber, 'V2.0+'),
                    _protRow('Tela Fantasma',             PlegmaColors.amber, 'V2.0+'),
                  ],
                ),
              ),
            ] else ...[
              const SizedBox(height: 8),
              GestureDetector(
                onTap: () async {
                  await showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    backgroundColor: PlegmaColors.bg2,
                    shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                    ),
                    builder: (_) => DraggableScrollableSheet(
                      expand: false,
                      initialChildSize: 0.92,
                      minChildSize: 0.5,
                      maxChildSize: 0.96,
                      builder: (ctx, scrollCtrl) => Column(
                        children: [
                          Center(
                            child: Container(
                              width: 36, height: 4,
                              margin: const EdgeInsets.symmetric(vertical: 12),
                              decoration: BoxDecoration(
                                color: PlegmaColors.border,
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                          ),
                          Expanded(
                            child: ListView(
                              controller: scrollCtrl,
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
                              children: [
                                _ShieldAtivacaoView(
                                  onAtivado: () {
                                    Navigator.of(ctx).pop();
                                    widget.onAtivado?.call();
                                  },
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        PlegmaColors.cyan.withValues(alpha: 0.08),
                        PlegmaColors.bg2,
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: PlegmaColors.cyanBord),
                  ),
                  child: Row(children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: PlegmaColors.cyan.withValues(alpha: 0.1),
                        shape: BoxShape.circle,
                        border: Border.all(color: PlegmaColors.cyanBord),
                      ),
                      child: const Icon(Icons.security, size: 22, color: PlegmaColors.cyan),
                    ),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('ATIVAR LATTICE SHIELD',
                              style: TextStyle(
                                  fontSize: 12, color: PlegmaColors.cyan,
                                  letterSpacing: 2, fontWeight: FontWeight.bold)),
                          SizedBox(height: 2),
                          Text('Conecte sua carteira e ative a proteção',
                              style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
                        ],
                      ),
                    ),
                    const Icon(Icons.arrow_upward, size: 14, color: PlegmaColors.textDim),
                  ]),
                ),
              ),
            ],
            const SizedBox(height: 24),
          ],
        ),

        // Scanner QR overlay
        if (_scanQR)
          Positioned.fill(
            child: Container(
              color: Colors.black,
              child: Stack(
                children: [
                  MobileScanner(
                    onDetect: (capture) {
                      if (_qrProcessando || _autenticando) return;
                      final barcode = capture.barcodes.firstOrNull;
                      if (barcode?.rawValue != null) _processarQR(barcode!.rawValue!);
                    },
                  ),
                  Center(
                    child: Container(
                      width: 240, height: 240,
                      decoration: BoxDecoration(
                        border: Border.all(color: PlegmaColors.cyan, width: 2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  Positioned(
                    bottom: 60, left: 0, right: 0,
                    child: Column(children: [
                      const Text('Aponte para o QR do Dashboard',
                          style: TextStyle(color: PlegmaColors.text, fontSize: 13)),
                      const SizedBox(height: 16),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          OutlinedButton.icon(
                            style: OutlinedButton.styleFrom(
                              side: const BorderSide(color: PlegmaColors.cyan),
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                            ),
                            icon: const Icon(Icons.content_paste, size: 14, color: PlegmaColors.cyan),
                            label: const Text('COLAR LINK',
                                style: TextStyle(color: PlegmaColors.cyan, fontSize: 11, letterSpacing: 1)),
                            onPressed: () async {
                              final data = await Clipboard.getData(Clipboard.kTextPlain);
                              final text = data?.text?.trim() ?? '';
                              if (text.contains('plegma://auth') || text.contains('nonce=')) {
                                _processarQR(text);
                              } else {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Nenhum link PLEGMA encontrado na área de transferência'),
                                    backgroundColor: PlegmaColors.bg2,
                                    duration: Duration(seconds: 2),
                                  ),
                                );
                              }
                            },
                          ),
                          const SizedBox(width: 12),
                          TextButton(
                            onPressed: () => setState(() => _scanQR = false),
                            child: const Text('CANCELAR',
                                style: TextStyle(color: PlegmaColors.red, letterSpacing: 2)),
                          ),
                        ],
                      ),
                    ]),
                  ),
                ],
              ),
            ),
          ),

        // Loading overlay biometria
        if (_autenticando)
          Positioned.fill(
            child: Container(
              color: Colors.black87,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(color: PlegmaColors.cyan),
                  const SizedBox(height: 20),
                  Text(_authStatus,
                      style: const TextStyle(color: PlegmaColors.text, fontSize: 13, letterSpacing: 1)),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _protRow(String label, Color cor, String status) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(children: [
      Expanded(child: Text(label,
          style: const TextStyle(fontSize: 12, color: PlegmaColors.text3))),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: cor.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: cor.withValues(alpha: 0.4)),
        ),
        child: Text(status,
            style: TextStyle(fontSize: 9, color: cor, letterSpacing: 1, fontWeight: FontWeight.bold)),
      ),
    ]),
  );

  Widget _specChip(String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(color: PlegmaColors.cyanDim, borderRadius: BorderRadius.circular(4)),
    child: Text(label, style: const TextStyle(fontSize: 10, color: PlegmaColors.cyan, letterSpacing: 1)),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Widget: Card de Status do Snapshot ZK
// ─────────────────────────────────────────────────────────────────────────────

class _SnapshotCard extends StatelessWidget {
  final Map<String, dynamic>? snapshot;
  final SnapshotDelta?        delta;
  final bool                  reancorando;
  final VoidCallback          onReancorar;

  const _SnapshotCard({
    required this.snapshot,
    required this.delta,
    required this.reancorando,
    required this.onReancorar,
  });

  String _ts(int ms) {
    final d = DateTime.fromMillisecondsSinceEpoch(ms);
    return '${d.day.toString().padLeft(2,'0')}/${d.month.toString().padLeft(2,'0')}/${d.year} '
           '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
  }

  @override
  Widget build(BuildContext context) {
    final temDelta = delta != null && delta!.temMudancas;

    if (snapshot == null) {
      return PlegmaCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.photo_camera, size: 15, color: PlegmaColors.textDim),
              const SizedBox(width: 8),
              const PlegmaLabel('Integridade ZK'),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: PlegmaColors.amber.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: PlegmaColors.amber.withValues(alpha: 0.4)),
                ),
                child: const Text('SEM SNAPSHOT',
                    style: TextStyle(fontSize: 9, color: PlegmaColors.amber,
                        letterSpacing: 1, fontWeight: FontWeight.bold)),
              ),
            ]),
            const SizedBox(height: 8),
            const Text('Nenhum snapshot de segurança criado. '
                'Crie um na próxima reinicialização ou vá em Configurações.',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim, height: 1.5)),
          ],
        ),
      );
    }

    final stateHash  = snapshot!['state_hash'] as String? ?? '';
    final anchorId   = snapshot!['anchor_id']  as String? ?? '';
    final appCount   = snapshot!['app_count']  as int?    ?? 0;
    final ts         = snapshot!['timestamp']  as int?    ?? 0;
    final zkEngine   = snapshot!['zk_engine']  as String? ?? '';

    return PlegmaCard(
      topAccent: temDelta ? PlegmaColors.red : PlegmaColors.green,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(
              temDelta ? Icons.warning_amber_rounded : Icons.verified_user,
              size: 15,
              color: temDelta ? PlegmaColors.red : PlegmaColors.green,
            ),
            const SizedBox(width: 8),
            const PlegmaLabel('Integridade ZK'),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              decoration: BoxDecoration(
                color: (temDelta ? PlegmaColors.red : PlegmaColors.green).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(
                    color: (temDelta ? PlegmaColors.red : PlegmaColors.green).withValues(alpha: 0.4)),
              ),
              child: Text(temDelta ? 'MUDANÇA DETECTADA' : 'ÍNTEGRO',
                  style: TextStyle(
                    fontSize: 9,
                    color: temDelta ? PlegmaColors.red : PlegmaColors.green,
                    letterSpacing: 1, fontWeight: FontWeight.bold,
                  )),
            ),
          ]),
          const SizedBox(height: 12),

          // Hash do estado
          _infoRow('Hash do estado',
              '${stateHash.substring(0, 16)}...${stateHash.substring(stateHash.length - 8)}'),
          _infoRow('Anchor ID',
              '${anchorId.substring(0, 12)}...${anchorId.substring(anchorId.length - 6)}'),
          _infoRow('Apps monitorados', '$appCount apps'),
          _infoRow('Ancorado em', ts > 0 ? _ts(ts) : '—'),
          _infoRow('ZK Engine', zkEngine),

          // Alerta de delta
          if (temDelta) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: PlegmaColors.red.withValues(alpha: 0.07),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: PlegmaColors.red.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('MUDANÇAS DETECTADAS',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.red,
                          letterSpacing: 2, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  if (delta!.adicionados.isNotEmpty)
                    _deltaRow(Icons.add_circle_outline, PlegmaColors.amber,
                        '${delta!.adicionados.length} instalado(s)', delta!.adicionados),
                  if (delta!.removidos.isNotEmpty)
                    _deltaRow(Icons.remove_circle_outline, PlegmaColors.textDim,
                        '${delta!.removidos.length} removido(s)', delta!.removidos),
                  if (delta!.alterados.isNotEmpty)
                    _deltaRow(Icons.change_circle_outlined, PlegmaColors.red,
                        '${delta!.alterados.length} re-assinado(s)', delta!.alterados),
                ],
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: reancorando ? null : onReancorar,
                style: ElevatedButton.styleFrom(
                  backgroundColor: PlegmaColors.cyan.withValues(alpha: 0.15),
                  side: const BorderSide(color: PlegmaColors.cyan),
                ),
                icon: reancorando
                    ? const SizedBox(width: 14, height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2, color: PlegmaColors.cyan))
                    : const Icon(Icons.verified_user, size: 16, color: PlegmaColors.cyan),
                label: const Text('APROVAR E RE-ANCORAR',
                    style: TextStyle(color: PlegmaColors.cyan)),
              ),
            ),
          ],

          // Sem delta: botão de re-ancoragem voluntária
          if (!temDelta) ...[
            const SizedBox(height: 10),
            GestureDetector(
              onTap: reancorando ? null : onReancorar,
              child: Row(children: [
                reancorando
                    ? const SizedBox(width: 12, height: 12,
                        child: CircularProgressIndicator(strokeWidth: 1.5, color: PlegmaColors.textDim))
                    : const Icon(Icons.refresh, size: 12, color: PlegmaColors.textDim),
                const SizedBox(width: 6),
                const Text('Atualizar snapshot',
                    style: TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
              ]),
            ),
          ],
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value) => Padding(
    padding: const EdgeInsets.only(bottom: 5),
    child: Row(children: [
      SizedBox(
        width: 120,
        child: Text(label,
            style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
      ),
      Expanded(
        child: Text(value,
            style: const TextStyle(fontSize: 10, color: PlegmaColors.text3,
                fontFamily: 'monospace')),
      ),
    ]),
  );

  Widget _deltaRow(IconData icon, Color color, String title, List<String> pkgs) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, size: 13, color: color),
              const SizedBox(width: 4),
              Text(title, style: TextStyle(fontSize: 11, color: color)),
            ]),
            ...pkgs.take(3).map((pkg) => Padding(
              padding: const EdgeInsets.only(left: 18, top: 2),
              child: Text(pkg,
                  style: TextStyle(fontSize: 9, color: color.withValues(alpha: 0.7)),
                  overflow: TextOverflow.ellipsis),
            )),
            if (pkgs.length > 3)
              Padding(
                padding: const EdgeInsets.only(left: 18, top: 2),
                child: Text('+ ${pkgs.length - 3} mais...',
                    style: TextStyle(fontSize: 9, color: color.withValues(alpha: 0.5))),
              ),
          ],
        ),
      );
}

// ─────────────────────────────────────────────────────────────────────────────
// ABA 2 — SCANNER  (Antivírus + Anti-Phishing)
// ─────────────────────────────────────────────────────────────────────────────

class _ScannerTab extends StatefulWidget {
  final bool shieldAtivo;
  const _ScannerTab({required this.shieldAtivo});
  @override
  State<_ScannerTab> createState() => _ScannerTabState();
}

class _ScannerTabState extends State<_ScannerTab> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  // ── App Scanner
  bool   _scanningApps = false;
  int    _appsTotal    = 0;
  int    _appsLimpos   = 0;
  List<Map<String, dynamic>> _appsFlagged = [];
  String _scanStatus   = '';

  // ── URL Checker
  final TextEditingController _urlCtrl = TextEditingController();
  bool   _checkingUrl = false;
  Map<String, dynamic>? _urlResult;

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _escanearApps() async {
    setState(() {
      _scanningApps = true;
      _scanStatus   = 'Lendo apps instalados...';
      _appsFlagged  = [];
      _appsTotal    = 0;
      _appsLimpos   = 0;
    });

    List<Map<String, dynamic>> apps = [];
    try {
      final raw = await _kShieldChannel.invokeMethod('getInstalledApps');
      apps = (raw as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } on PlatformException catch (e) {
      setState(() {
        _scanningApps = false;
        _scanStatus   = '✗ Erro ao ler apps: ${e.message}';
      });
      return;
    }

    setState(() => _scanStatus = 'Verificando ${apps.length} apps no servidor...');

    final payload = apps.map((a) => {
      'package_name': a['package_name'] as String,
      'cert_hash'   : a['cert_hash'] as String? ?? '',
    }).toList();

    final result = await ApiService.shieldScanBatch(payload);

    if (result == null) {
      // Offline: faz verificação local heurística
      final flagged = <Map<String, dynamic>>[];
      for (final a in apps) {
        final pkg = (a['package_name'] as String).toLowerCase();
        final suspiciousTerms = ['spy', 'keylog', 'stealer', 'botnet', 'trojan', 'banker', 'rat.'];
        if (suspiciousTerms.any((t) => pkg.contains(t))) {
          flagged.add({'pacote': a['package_name'], 'status': 'SUSPEITO', 'risco': 'MÉDIO', 'motivo': 'nome_suspeito_offline'});
        }
      }
      setState(() {
        _scanningApps = false;
        _appsTotal    = apps.length;
        _appsLimpos   = apps.length - flagged.length;
        _appsFlagged  = flagged;
        _scanStatus   = flagged.isEmpty
            ? '✓ Scan offline — ${apps.length} apps verificados'
            : '⚠ Servidor offline — ${flagged.length} suspeito(s) por heurística';
      });
      return;
    }

    final flagged = (result['flagged'] as List? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();

    setState(() {
      _scanningApps = false;
      _appsTotal    = result['total_escaneado'] as int? ?? apps.length;
      _appsLimpos   = _appsTotal - flagged.length;
      _appsFlagged  = flagged;
      _scanStatus   = flagged.isEmpty
          ? '✓ Nenhuma ameaça encontrada'
          : '⚠ ${flagged.length} ameaça(s) detectada(s)';
    });
  }

  Future<void> _verificarUrl() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    setState(() { _checkingUrl = true; _urlResult = null; });

    final result = await ApiService.shieldScanUrl(url);

    if (result == null) {
      // Fallback offline: verificação básica
      final lower = url.toLowerCase();
      final Map<String, dynamic> offline;
      if (RegExp(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}').hasMatch(lower)) {
        offline = {'status': 'SUSPEITO', 'risco': 'MÉDIO', 'motivo': 'url_ip_direto_offline'};
      } else if (lower.contains('seed') && lower.contains('phrase') ||
                 lower.contains('private') && lower.contains('key')) {
        offline = {'status': 'SUSPEITO', 'risco': 'MÉDIO', 'motivo': 'padrao_phishing_offline'};
      } else {
        offline = {'status': 'INDISPONÍVEL', 'risco': '—', 'motivo': 'servidor_offline'};
      }
      setState(() { _checkingUrl = false; _urlResult = offline; });
      return;
    }

    setState(() { _checkingUrl = false; _urlResult = result; });
  }

  Future<void> _reportarAmeaca(String tipo, String valor) async {
    await ApiService.shieldReport(tipo, valor);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ameaça reportada à rede')),
      );
    }
  }

  Color _riscoColor(String? risco) {
    switch (risco) {
      case 'ALTO':  return PlegmaColors.red;
      case 'MÉDIO': return PlegmaColors.amber;
      default:      return PlegmaColors.green;
    }
  }

  Color _statusColor(String? status) {
    switch (status) {
      case 'BLOQUEADO':
      case 'MALWARE':   return PlegmaColors.red;
      case 'SUSPEITO':  return PlegmaColors.amber;
      case 'SEGURO':
      case 'LIMPO':     return PlegmaColors.green;
      default:          return PlegmaColors.textDim;
    }
  }

  Widget _buildLockedOverlay(Widget content) => Stack(
    children: [
      IgnorePointer(child: Opacity(opacity: 0.55, child: content)),
      Positioned.fill(
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.black.withValues(alpha: 0.15),
                Colors.black.withValues(alpha: 0.45),
              ],
            ),
          ),
        ),
      ),
      Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: PlegmaColors.bg2,
                shape: BoxShape.circle,
                border: Border.all(color: PlegmaColors.cyanBord, width: 1.5),
              ),
              child: const Icon(Icons.lock_outline, size: 32, color: PlegmaColors.cyan),
            ),
            const SizedBox(height: 14),
            const Text('RECURSO BLOQUEADO',
                style: TextStyle(fontSize: 11, color: PlegmaColors.text,
                    letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const Text('Ative o Shield na aba AUTENTICAR',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
          ],
        ),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final content = ListView(
      padding: const EdgeInsets.all(16),
      children: [

        // ── Scanner de Apps ─────────────────────────────────────────
        if (!kIsWeb)
          PlegmaCard(
            topAccent: PlegmaColors.cyan,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.security, size: 16, color: PlegmaColors.cyan),
                  const SizedBox(width: 8),
                  const PlegmaLabel('Scanner de Apps'),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: PlegmaColors.green.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: PlegmaColors.green.withValues(alpha: 0.4)),
                    ),
                    child: const Text('ATIVO',
                        style: TextStyle(fontSize: 9, color: PlegmaColors.green, letterSpacing: 1, fontWeight: FontWeight.bold)),
                  ),
                ]),
                const SizedBox(height: 8),
                const Text(
                  'Verifica todos os apps instalados contra a base de malware da rede PLEGMA. '
                  'Assinaturas distribuídas via DAG — atualização sem servidor central.',
                  style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
                ),
                const SizedBox(height: 14),

                // Resultado do scan
                if (_appsTotal > 0 && !_scanningApps) ...[
                  Row(children: [
                    _statChip('$_appsTotal', 'escaneados', PlegmaColors.cyan),
                    const SizedBox(width: 8),
                    _statChip('$_appsLimpos', 'limpos', PlegmaColors.green),
                    const SizedBox(width: 8),
                    _statChip('${_appsFlagged.length}', 'ameaças', _appsFlagged.isEmpty ? PlegmaColors.textDim : PlegmaColors.red),
                  ]),
                  const SizedBox(height: 10),
                ],

                if (_scanStatus.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Text(_scanStatus,
                        style: TextStyle(
                          fontSize: 11, letterSpacing: 0.5,
                          color: _scanStatus.startsWith('✓') ? PlegmaColors.green
                               : _scanStatus.startsWith('✗') ? PlegmaColors.red
                               : PlegmaColors.amber,
                        )),
                  ),

                // Lista de apps flagged
                if (_appsFlagged.isNotEmpty) ...[
                  const Text('AMEAÇAS DETECTADAS',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.red, letterSpacing: 2)),
                  const SizedBox(height: 8),
                  ..._appsFlagged.map((app) => _appThreatTile(app)),
                  const SizedBox(height: 8),
                ],

                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _scanningApps ? null : _escanearApps,
                    icon: _scanningApps
                        ? const SizedBox(width: 14, height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2, color: PlegmaColors.cyan))
                        : const Icon(Icons.radar, size: 16),
                    label: Text(_scanningApps ? 'ESCANEANDO...' : 'ESCANEAR TODOS OS APPS'),
                  ),
                ),
              ],
            ),
          )
        else
          PlegmaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                PlegmaLabel('Scanner de Apps'),
                SizedBox(height: 8),
                Text(
                  'Disponível no app Android. Verifica todos os apps instalados '
                  'contra a base de malware da rede PLEGMA via DAG.',
                  style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
                ),
              ],
            ),
          ),
        const SizedBox(height: 14),

        // ── Verificador de URL ──────────────────────────────────────
        PlegmaCard(
          topAccent: PlegmaColors.purple,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.link_off, size: 16, color: PlegmaColors.purple),
                const SizedBox(width: 8),
                const PlegmaLabel('Verificador de URL'),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: PlegmaColors.green.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: PlegmaColors.green.withValues(alpha: 0.4)),
                  ),
                  child: const Text('ATIVO',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.green, letterSpacing: 1, fontWeight: FontWeight.bold)),
                ),
              ]),
              const SizedBox(height: 8),
              const Text(
                'Cole qualquer URL ou domínio para verificar contra a base de phishing, '
                'spam e sites maliciosos conhecidos pela rede PLEGMA.',
                style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
              ),
              const SizedBox(height: 14),

              // Input URL
              TextField(
                controller: _urlCtrl,
                style: const TextStyle(fontSize: 12, color: PlegmaColors.text),
                decoration: InputDecoration(
                  hintText: 'https://exemplo.com ou dominio.com',
                  hintStyle: const TextStyle(fontSize: 11, color: PlegmaColors.textDim),
                  filled: true,
                  fillColor: PlegmaColors.bg3,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(6),
                    borderSide: BorderSide(color: PlegmaColors.purple.withValues(alpha: 0.4)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(6),
                    borderSide: BorderSide(color: PlegmaColors.purple.withValues(alpha: 0.3)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(6),
                    borderSide: const BorderSide(color: PlegmaColors.purple),
                  ),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.clear, size: 16, color: PlegmaColors.textDim),
                    onPressed: () { _urlCtrl.clear(); setState(() => _urlResult = null); },
                  ),
                ),
                onSubmitted: (_) => _verificarUrl(),
              ),
              const SizedBox(height: 10),

              // Resultado
              if (_urlResult != null) _urlResultCard(_urlResult!),
              if (_urlResult != null) const SizedBox(height: 10),

              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: PlegmaColors.purple.withValues(alpha: 0.2),
                    side: const BorderSide(color: PlegmaColors.purple),
                  ),
                  onPressed: _checkingUrl ? null : _verificarUrl,
                  icon: _checkingUrl
                      ? const SizedBox(width: 14, height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: PlegmaColors.purple))
                      : const Icon(Icons.search, size: 16, color: PlegmaColors.purple),
                  label: const Text('VERIFICAR URL',
                      style: TextStyle(color: PlegmaColors.purple)),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
    if (!widget.shieldAtivo) return _buildLockedOverlay(content);
    return content;
  }

  Widget _statChip(String value, String label, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: color.withValues(alpha: 0.3)),
    ),
    child: Column(children: [
      Text(value, style: TextStyle(fontSize: 16, color: color, fontWeight: FontWeight.bold)),
      Text(label, style: TextStyle(fontSize: 9, color: color.withValues(alpha: 0.7), letterSpacing: 1)),
    ]),
  );

  Widget _appThreatTile(Map<String, dynamic> app) {
    final status = app['status'] as String? ?? '';
    final cor = _statusColor(status);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: cor.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: cor.withValues(alpha: 0.3)),
      ),
      child: Row(children: [
        Icon(Icons.warning_amber_rounded, size: 16, color: cor),
        const SizedBox(width: 8),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(app['pacote'] as String? ?? '',
                style: const TextStyle(fontSize: 11, color: PlegmaColors.text)),
            Text(app['motivo'] as String? ?? '',
                style: TextStyle(fontSize: 10, color: cor.withValues(alpha: 0.8))),
          ],
        )),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: cor.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(status,
              style: TextStyle(fontSize: 9, color: cor, fontWeight: FontWeight.bold)),
        ),
        const SizedBox(width: 6),
        GestureDetector(
          onTap: () => _reportarAmeaca('package', app['pacote'] as String? ?? ''),
          child: const Icon(Icons.report_gmailerrorred, size: 16, color: PlegmaColors.textDim),
        ),
      ]),
    );
  }

  Widget _urlResultCard(Map<String, dynamic> res) {
    final status = res['status'] as String? ?? '';
    final risco  = res['risco']  as String? ?? '';
    final motivo = res['motivo'] as String? ?? '';
    final cor    = _statusColor(status);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cor.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cor.withValues(alpha: 0.4)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(
          status == 'SEGURO' || status == 'LIMPO'
              ? Icons.check_circle_outline
              : status == 'SUSPEITO'
                  ? Icons.warning_amber_rounded
                  : Icons.block,
          color: cor, size: 22,
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(status, style: TextStyle(fontSize: 14, color: cor, fontWeight: FontWeight.bold, letterSpacing: 1)),
            const SizedBox(height: 2),
            Text('Risco: $risco', style: TextStyle(fontSize: 11, color: _riscoColor(risco))),
            const SizedBox(height: 2),
            Text(motivo.replaceAll('_', ' '),
                style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
          ],
        )),
        if (status == 'SUSPEITO' || status == 'BLOQUEADO')
          GestureDetector(
            onTap: () {
              final domain = res['dominio'] as String? ?? _urlCtrl.text.trim();
              _reportarAmeaca('domain', domain);
            },
            child: const Icon(Icons.report_gmailerrorred, size: 18, color: PlegmaColors.textDim),
          ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ABA 3 — PERMISSÕES  (Monitor de processos / acesso a recursos)
// ─────────────────────────────────────────────────────────────────────────────

class _PermissoesTab extends StatefulWidget {
  final bool shieldAtivo;
  const _PermissoesTab({required this.shieldAtivo});
  @override
  State<_PermissoesTab> createState() => _PermissoesTabState();
}

class _PermissoesTabState extends State<_PermissoesTab> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  bool   _carregando = false;
  String _status     = '';
  List<Map<String, dynamic>> _apps = [];

  // Mapa de ícone/cor por permissão
  static const _permInfo = {
    'CAMERA'               : {'label': 'Câmera',          'icon': Icons.camera_alt},
    'RECORD_AUDIO'         : {'label': 'Microfone',        'icon': Icons.mic},
    'ACCESS_FINE_LOCATION' : {'label': 'Localização GPS',  'icon': Icons.gps_fixed},
    'ACCESS_COARSE_LOCATION': {'label': 'Localização',     'icon': Icons.location_on},
    'READ_CONTACTS'        : {'label': 'Contatos',         'icon': Icons.contacts},
    'READ_SMS'             : {'label': 'Leitura SMS',      'icon': Icons.sms},
    'SEND_SMS'             : {'label': 'Envio SMS',        'icon': Icons.send},
    'READ_CALL_LOG'        : {'label': 'Histórico Chamadas', 'icon': Icons.call},
    'READ_PHONE_STATE'     : {'label': 'Estado do Telefone', 'icon': Icons.phone_android},
    'READ_MEDIA_IMAGES'    : {'label': 'Fotos/Mídia',      'icon': Icons.photo},
    'READ_EXTERNAL_STORAGE': {'label': 'Armazenamento',    'icon': Icons.folder},
  };

  int get _alto   => _apps.where((a) => _riscoApp(a) == 'ALTO').length;
  int get _medio  => _apps.where((a) => _riscoApp(a) == 'MÉDIO').length;

  String _riscoApp(Map<String, dynamic> app) {
    final perms       = (app['permissions'] as List).cast<String>().toSet();
    final whileInUse  = ((app['permissions_while_in_use'] as List?)?.cast<String>() ?? []).toSet();

    // SMS/chamadas = sempre ALTO (não há "somente quando em uso")
    const sempreAlto  = {'READ_SMS', 'SEND_SMS', 'READ_CALL_LOG'};
    if (perms.any((p) => sempreAlto.contains(p))) return 'ALTO';

    // Câmera/mic "sempre ativo" = ALTO; "somente quando em uso" = MÉDIO
    const checkGrant  = {'CAMERA', 'RECORD_AUDIO'};
    for (final p in checkGrant) {
      if (perms.contains(p) && !whileInUse.contains(p)) return 'ALTO';
    }

    if (perms.length >= 3) return 'MÉDIO';
    return 'BAIXO';
  }

  Future<void> _abrirConfiguracoes(String packageName) async {
    try {
      await _kShieldChannel.invokeMethod('openAppSettings', packageName);
    } catch (e) { debugPrint('Erro: $e'); }
  }

  Future<void> _carregarPermissoes() async {
    setState(() { _carregando = true; _status = 'Analisando permissões...'; _apps = []; });

    try {
      final raw = await _kShieldChannel.invokeMethod('getAppsWithSensitivePermissions');
      final apps = (raw as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();

      // Ordena: ALTO > MÉDIO > BAIXO
      apps.sort((a, b) {
        const order = {'ALTO': 0, 'MÉDIO': 1, 'BAIXO': 2};
        return (order[_riscoApp(a)] ?? 2).compareTo(order[_riscoApp(b)] ?? 2);
      });

      setState(() {
        _carregando = false;
        _apps       = apps;
        _status     = apps.isEmpty
            ? '✓ Nenhum app com permissões sensíveis encontrado'
            : '${apps.length} app(s) com permissões sensíveis';
      });
    } on PlatformException catch (e) {
      setState(() {
        _carregando = false;
        _status     = '✗ Erro: ${e.message}';
      });
    }
  }

  Widget _permChip(IconData icon, String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
    decoration: BoxDecoration(
      color: PlegmaColors.bg,
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: PlegmaColors.amber.withValues(alpha: 0.25)),
    ),
    child: Row(children: [
      Icon(icon, size: 14, color: PlegmaColors.amber),
      const SizedBox(width: 6),
      Expanded(child: Text(label,
          style: const TextStyle(fontSize: 10, color: PlegmaColors.text3))),
    ]),
  );

  Widget _buildLockedOverlay(Widget content) => Stack(
    children: [
      IgnorePointer(child: Opacity(opacity: 0.55, child: content)),
      Positioned.fill(
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.black.withValues(alpha: 0.15),
                Colors.black.withValues(alpha: 0.45),
              ],
            ),
          ),
        ),
      ),
      Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: PlegmaColors.bg2,
                shape: BoxShape.circle,
                border: Border.all(color: PlegmaColors.cyanBord, width: 1.5),
              ),
              child: const Icon(Icons.lock_outline, size: 32, color: PlegmaColors.cyan),
            ),
            const SizedBox(height: 14),
            const Text('RECURSO BLOQUEADO',
                style: TextStyle(fontSize: 11, color: PlegmaColors.text,
                    letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const Text('Ative o Shield na aba AUTENTICAR',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
          ],
        ),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (kIsWeb) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          PlegmaCard(
            topAccent: PlegmaColors.amber,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: const [
                  Icon(Icons.manage_search, size: 16, color: PlegmaColors.amber),
                  SizedBox(width: 8),
                  PlegmaLabel('Monitor de Permissões'),
                  Spacer(),
                  StatusBadge(label: 'ANDROID', color: PlegmaColors.amber),
                ]),
                const SizedBox(height: 12),
                const Text(
                  'Detecta apps de terceiros com acesso ativo à câmera, microfone, '
                  'localização, contatos ou SMS.\n\n'
                  'Funcionalidade disponível no app Android — requer acesso nativo '
                  'ao PackageManager do sistema.',
                  style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
                ),
                const SizedBox(height: 16),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 8,
                  crossAxisSpacing: 8,
                  childAspectRatio: 3.2,
                  children: [
                    _permChip(Icons.camera_alt,   'Câmera'),
                    _permChip(Icons.mic,           'Microfone'),
                    _permChip(Icons.gps_fixed,     'Localização GPS'),
                    _permChip(Icons.contacts,      'Contatos'),
                    _permChip(Icons.sms,           'Leitura SMS'),
                    _permChip(Icons.call,          'Histórico Chamadas'),
                    _permChip(Icons.phone_android, 'Estado Telefone'),
                    _permChip(Icons.folder,        'Armazenamento'),
                  ],
                ),
              ],
            ),
          ),
        ],
      );
    }
    final content = ListView(
      padding: const EdgeInsets.all(16),
      children: [

        PlegmaCard(
          topAccent: PlegmaColors.amber,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.manage_search, size: 16, color: PlegmaColors.amber),
                const SizedBox(width: 8),
                const PlegmaLabel('Monitor de Permissões'),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: PlegmaColors.green.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: PlegmaColors.green.withValues(alpha: 0.4)),
                  ),
                  child: const Text('ATIVO',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.green, letterSpacing: 1, fontWeight: FontWeight.bold)),
                ),
              ]),
              const SizedBox(height: 8),
              const Text(
                'Detecta apps de terceiros com acesso ativo à câmera, microfone, '
                'localização, contatos ou SMS. Mostra o que cada app pode fazer no '
                'seu dispositivo sem você perceber.',
                style: TextStyle(fontSize: 12, color: PlegmaColors.textDim, height: 1.6),
              ),
              const SizedBox(height: 14),

              // Resumo
              if (_apps.isNotEmpty && !_carregando) ...[
                Row(children: [
                  _riscoChip('$_alto',  'Alto Risco',  PlegmaColors.red),
                  const SizedBox(width: 8),
                  _riscoChip('$_medio', 'Médio Risco', PlegmaColors.amber),
                  const SizedBox(width: 8),
                  _riscoChip('${_apps.length - _alto - _medio}', 'Baixo Risco', PlegmaColors.textDim),
                ]),
                const SizedBox(height: 12),
              ],

              if (_status.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(_status,
                      style: TextStyle(
                        fontSize: 11, letterSpacing: 0.5,
                        color: _status.startsWith('✓') ? PlegmaColors.green
                             : _status.startsWith('✗') ? PlegmaColors.red
                             : PlegmaColors.amber,
                      )),
                ),

              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: PlegmaColors.amber.withValues(alpha: 0.15),
                    side: const BorderSide(color: PlegmaColors.amber),
                  ),
                  onPressed: _carregando ? null : _carregarPermissoes,
                  icon: _carregando
                      ? const SizedBox(width: 14, height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: PlegmaColors.amber))
                      : const Icon(Icons.manage_search, size: 16, color: PlegmaColors.amber),
                  label: const Text('ANALISAR PERMISSÕES',
                      style: TextStyle(color: PlegmaColors.amber)),
                ),
              ),
            ],
          ),
        ),

        // Lista de apps
        if (_apps.isNotEmpty) ...[
          const SizedBox(height: 12),
          ..._apps.map((app) => _appPermTile(app)),
        ],

        const SizedBox(height: 24),
      ],
    );
    if (!widget.shieldAtivo) return _buildLockedOverlay(content);
    return content;
  }

  Widget _riscoChip(String value, String label, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: color.withValues(alpha: 0.3)),
    ),
    child: Column(children: [
      Text(value, style: TextStyle(fontSize: 16, color: color, fontWeight: FontWeight.bold)),
      Text(label, style: TextStyle(fontSize: 9, color: color.withValues(alpha: 0.7), letterSpacing: 0.5)),
    ]),
  );

  Widget _appPermTile(Map<String, dynamic> app) {
    final perms      = (app['permissions'] as List).cast<String>();
    final whileInUse = ((app['permissions_while_in_use'] as List?)?.cast<String>() ?? []).toSet();
    final risco      = _riscoApp(app);
    final cor        = risco == 'ALTO' ? PlegmaColors.red
                     : risco == 'MÉDIO' ? PlegmaColors.amber
                     : PlegmaColors.textDim;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: PlegmaColors.bg2,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cor.withValues(alpha: 0.25)),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          leading: CircleAvatar(
            radius: 16,
            backgroundColor: cor.withValues(alpha: 0.1),
            child: Icon(Icons.apps, size: 16, color: cor),
          ),
          title: Text(app['app_name'] as String? ?? '',
              style: const TextStyle(fontSize: 12, color: PlegmaColors.text, fontWeight: FontWeight.w500)),
          subtitle: Text(app['package_name'] as String? ?? '',
              style: const TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 0.5)),
          trailing: Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
            decoration: BoxDecoration(
              color: cor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: cor.withValues(alpha: 0.4)),
            ),
            child: Text(risco,
                style: TextStyle(fontSize: 9, color: cor, fontWeight: FontWeight.bold, letterSpacing: 1)),
          ),
          children: [
            const Divider(height: 1, color: Color(0x22FFFFFF)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: perms.map((perm) {
                final info        = _permInfo[perm];
                final label       = info?['label'] as String?  ?? perm;
                final icon        = info?['icon']  as IconData? ?? Icons.lock;
                const altoR       = {'READ_SMS', 'SEND_SMS', 'READ_CALL_LOG'};
                const checkGrant  = {'CAMERA', 'RECORD_AUDIO'};
                final isAlto = altoR.contains(perm) ||
                    (checkGrant.contains(perm) && !whileInUse.contains(perm));
                final pColor  = isAlto ? PlegmaColors.red : PlegmaColors.amber;
                final tagLabel = (checkGrant.contains(perm) && whileInUse.contains(perm))
                    ? '$label · em uso' : label;
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: pColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: pColor.withValues(alpha: 0.3)),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(icon, size: 11, color: pColor),
                    const SizedBox(width: 4),
                    Text(tagLabel, style: TextStyle(fontSize: 10, color: pColor)),
                  ]),
                );
              }).toList(),
            ),
            const SizedBox(height: 10),

            // ── Botão: abrir configurações de permissão do app ──
            if (risco == 'ALTO' || risco == 'MÉDIO') ...[
              GestureDetector(
                onTap: () => _mostrarDicaPermissao(context, app),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                  decoration: BoxDecoration(
                    color: PlegmaColors.cyan.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: PlegmaColors.cyanBord),
                  ),
                  child: Row(children: const [
                    Icon(Icons.tune, size: 13, color: PlegmaColors.cyan),
                    SizedBox(width: 6),
                    Expanded(
                      child: Text('Como reduzir o risco desta permissão',
                          style: TextStyle(fontSize: 10, color: PlegmaColors.cyan)),
                    ),
                    Icon(Icons.arrow_forward_ios, size: 10, color: PlegmaColors.textDim),
                  ]),
                ),
              ),
              const SizedBox(height: 6),
            ],

            GestureDetector(
              onTap: () => _reportarApp(app['package_name'] as String? ?? ''),
              child: Row(children: const [
                Icon(Icons.report_gmailerrorred, size: 13, color: PlegmaColors.textDim),
                SizedBox(width: 4),
                Text('Reportar como suspeito',
                    style: TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
              ]),
            ),
          ],
        ),
      ),
    );
  }

  void _mostrarDicaPermissao(BuildContext context, Map<String, dynamic> app) {
    final packageName = app['package_name'] as String? ?? '';
    final appName     = app['app_name']     as String? ?? packageName;
    final perms       = (app['permissions'] as List).cast<String>();
    final whileInUse  = ((app['permissions_while_in_use'] as List?)?.cast<String>() ?? []).toSet();
    final temCamera   = perms.contains('CAMERA');
    final temMic      = perms.contains('RECORD_AUDIO');
    final camSempre   = temCamera && !whileInUse.contains('CAMERA');
    final micSempre   = temMic    && !whileInUse.contains('RECORD_AUDIO');

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: PlegmaColors.bg2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: PlegmaColors.cyanBord),
        ),
        title: Row(children: [
          const Icon(Icons.tune, size: 18, color: PlegmaColors.cyan),
          const SizedBox(width: 8),
          Expanded(child: Text(appName,
              style: const TextStyle(fontSize: 13, color: PlegmaColors.text,
                  fontWeight: FontWeight.bold),
              overflow: TextOverflow.ellipsis)),
        ]),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (camSempre || micSempre) ...[
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: PlegmaColors.red.withValues(alpha: 0.07),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: PlegmaColors.red.withValues(alpha: 0.25)),
                ),
                child: Text(
                  '${camSempre && micSempre ? "Câmera e Microfone estão" : camSempre ? "A Câmera está" : "O Microfone está"} '
                  'com acesso SEMPRE ATIVO.\n\n'
                  'Isso permite que o app grave mesmo quando está em segundo plano.\n\n'
                  'Recomendamos alterar para "Somente quando em uso".',
                  style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim, height: 1.6),
                ),
              ),
              const SizedBox(height: 12),
            ],
            const Text('Passo a passo:',
                style: TextStyle(fontSize: 11, color: PlegmaColors.text, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            _dicaPasso('1', 'Toque em "Abrir Configurações" abaixo'),
            _dicaPasso('2', 'Selecione "Permissões"'),
            _dicaPasso('3', 'Toque em Câmera ou Microfone'),
            _dicaPasso('4', 'Altere de "Permitir sempre" para "Somente quando em uso"'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('FECHAR',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim, letterSpacing: 1)),
          ),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.of(context).pop();
              _abrirConfiguracoes(packageName);
            },
            icon: const Icon(Icons.open_in_new, size: 14),
            label: const Text('ABRIR CONFIGURAÇÕES',
                style: TextStyle(fontSize: 11, letterSpacing: 1)),
          ),
        ],
      ),
    );
  }

  Widget _dicaPasso(String num, String texto) => Padding(
    padding: const EdgeInsets.only(bottom: 5),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        width: 18, height: 18,
        margin: const EdgeInsets.only(right: 8, top: 1),
        decoration: BoxDecoration(
          color: PlegmaColors.cyan.withValues(alpha: 0.15),
          shape: BoxShape.circle,
          border: Border.all(color: PlegmaColors.cyanBord),
        ),
        child: Center(
          child: Text(num, style: const TextStyle(fontSize: 9, color: PlegmaColors.cyan,
              fontWeight: FontWeight.bold)),
        ),
      ),
      Expanded(child: Text(texto,
          style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim, height: 1.5))),
    ]),
  );

  Future<void> _reportarApp(String packageName) async {
    await ApiService.shieldReport('package', packageName);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('App reportado à rede PLEGMA')),
      );
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Seletor de Método de Pagamento
// ─────────────────────────────────────────────────────────────────────────────

class _PaymentSelector extends StatelessWidget {
  final Map<String, dynamic>? payInfo;
  final String metodoSelecionado;
  final ValueChanged<String> onChanged;

  const _PaymentSelector({
    required this.payInfo,
    required this.metodoSelecionado,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final genesisAtivo   = payInfo?['genesis_ativo']    == true;
    final ehValidador    = payInfo?['eh_validador']     == true;
    final saldo          = (payInfo?['saldo_plg']       as num?)?.toDouble() ?? 0.0;
    final preco          = (payInfo?['preco_plg']       as num?)?.toDouble() ?? 1200.0;
    final saldoOk        = payInfo?['saldo_suficiente'] == true;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [

        // Genesis grátis
        if (genesisAtivo)
          _payCard(
            metodo   : 'gratis_genesis',
            icon     : Icons.rocket_launch_outlined,
            cor      : PlegmaColors.amber,
            titulo   : 'GRÁTIS — Fase Genesis',
            subtitulo: '30 dias gratuitos para usuários Genesis',
            badge    : 'GRÁTIS',
            badgeCor : PlegmaColors.amber,
            habilitado: true,
          ),

        // Desconto da mineração (só validadores)
        if (ehValidador)
          _payCard(
            metodo   : 'mineracao',
            icon     : Icons.bolt_outlined,
            cor      : PlegmaColors.cyan,
            titulo   : 'Descontar da Mineração',
            subtitulo: '${preco.toStringAsFixed(0)} PLG debitados das suas recompensas',
            badge    : 'VALIDADOR',
            badgeCor : PlegmaColors.cyan,
            habilitado: true,
          ),

        // Pagar com carteira — só mostra se não for validador
        if (!ehValidador)
          _payCard(
            metodo   : 'carteira',
            icon     : Icons.account_balance_wallet_outlined,
            cor      : saldoOk ? PlegmaColors.amber : PlegmaColors.red,
            titulo   : saldoOk
                ? 'Pagar com Carteira PLG — será debitado'
                : 'Pagar com Carteira PLG — saldo insuficiente',
            subtitulo: saldoOk
                ? 'Serão debitados ${preco.toStringAsFixed(0)} PLG (≈ US\$ 12) ao ativar'
                : 'Saldo: ${saldo.toStringAsFixed(0)} PLG  •  Necessário: ${preco.toStringAsFixed(0)} PLG',
            badge    : saldoOk ? 'DÉBITO PLG' : 'INSUFICIENTE',
            badgeCor : saldoOk ? PlegmaColors.amber : PlegmaColors.red,
            habilitado: saldoOk,
          ),
      ],
    );
  }

  Widget _payCard({
    required String   metodo,
    required IconData icon,
    required Color    cor,
    required String   titulo,
    required String   subtitulo,
    required String   badge,
    required Color    badgeCor,
    required bool     habilitado,
  }) {
    final selecionado = metodoSelecionado == metodo;
    return GestureDetector(
      onTap: habilitado ? () => onChanged(metodo) : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: selecionado
              ? cor.withValues(alpha: 0.12)
              : PlegmaColors.bg.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: selecionado ? cor : PlegmaColors.border,
            width: selecionado ? 1.5 : 1,
          ),
        ),
        child: Row(children: [
          Icon(icon, size: 20, color: habilitado ? cor : PlegmaColors.textDim),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(titulo,
                  style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.bold,
                    color: habilitado ? PlegmaColors.text : PlegmaColors.textDim,
                  )),
              const SizedBox(height: 2),
              Text(subtitulo,
                  style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
            ]),
          ),
          const SizedBox(width: 8),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color       : badgeCor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(3),
                border      : Border.all(color: badgeCor.withValues(alpha: 0.4)),
              ),
              child: Text(badge,
                  style: TextStyle(
                      fontSize: 8, color: badgeCor,
                      letterSpacing: 0.8, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(height: 4),
            Icon(
              selecionado ? Icons.radio_button_checked : Icons.radio_button_unchecked,
              size: 16,
              color: selecionado ? cor : PlegmaColors.textDim,
            ),
          ]),
        ]),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Animação de Ativação — estilo Xiaomi carregamento
// ─────────────────────────────────────────────────────────────────────────────

class _ActivationOverlay extends StatefulWidget {
  final Future<void> workFuture;
  const _ActivationOverlay({required this.workFuture});

  @override
  State<_ActivationOverlay> createState() => _ActivationOverlayState();
}

class _ActivationOverlayState extends State<_ActivationOverlay> {
  double  _progresso = 0.0;
  bool    _concluido = false;
  bool    _erro      = false;
  String? _erroMsg;
  Timer?  _timer;

  static const _fases = [
    (0.00, 'Iniciando protocolo...'),
    (0.15, 'Verificando carteira...'),
    (0.30, 'Registrando assinatura...'),
    (0.50, 'Criando snapshot ZK...'),
    (0.70, 'Ancorando na rede DAG...'),
    (0.88, 'Finalizando proteção...'),
  ];

  String get _faseAtual {
    for (var i = _fases.length - 1; i >= 0; i--) {
      if (_progresso >= _fases[i].$1) return _fases[i].$2;
    }
    return _fases[0].$2;
  }

  @override
  void initState() {
    super.initState();
    // Avança até 90% em ~3.5 s (70 ticks × 50 ms)
    _timer = Timer.periodic(const Duration(milliseconds: 50), (t) {
      if (!mounted || _concluido) { t.cancel(); return; }
      if (_progresso < 0.90) {
        setState(() => _progresso = (_progresso + 0.90 / 70).clamp(0.0, 0.90));
      }
    });

    widget.workFuture.then((_) async {
      _timer?.cancel();
      for (double p = _progresso; p <= 1.0; p += 0.025) {
        if (!mounted) return;
        setState(() => _progresso = p.clamp(0.0, 1.0));
        await Future.delayed(const Duration(milliseconds: 25));
      }
      if (!mounted) return;
      setState(() { _progresso = 1.0; _concluido = true; });
      await Future.delayed(const Duration(milliseconds: 900));
      if (mounted) Navigator.of(context).pop(true);
    }).catchError((e) async {
      _timer?.cancel();
      if (!mounted) return;
      setState(() { _erro = true; _erroMsg = e.toString().replaceFirst('Exception: ', ''); });
      await Future.delayed(const Duration(seconds: 3));
      if (mounted) Navigator.of(context).pop(false);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pct = (_progresso * 100).round();
    return Material(
      color: Colors.black,
      child: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // ── Anéis concêntricos + percentual ──
              SizedBox(
                width: 220, height: 220,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 210, height: 210,
                      child: CircularProgressIndicator(
                        value: _progresso,
                        strokeWidth: 3.5,
                        color: _concluido ? PlegmaColors.green : PlegmaColors.cyan,
                        backgroundColor: PlegmaColors.cyan.withValues(alpha: 0.07),
                      ),
                    ),
                    SizedBox(
                      width: 170, height: 170,
                      child: CircularProgressIndicator(
                        value: (_progresso * 1.3).clamp(0.0, 1.0),
                        strokeWidth: 1.5,
                        color: PlegmaColors.cyan.withValues(alpha: 0.30),
                        backgroundColor: Colors.transparent,
                      ),
                    ),
                    SizedBox(
                      width: 130, height: 130,
                      child: CircularProgressIndicator(
                        value: (_progresso * 1.8).clamp(0.0, 1.0),
                        strokeWidth: 1.0,
                        color: PlegmaColors.cyan.withValues(alpha: 0.15),
                        backgroundColor: Colors.transparent,
                      ),
                    ),
                    // Centro: ícone ou número
                    _concluido
                        ? const Icon(Icons.verified_user,
                            size: 58, color: PlegmaColors.green)
                        : _erro
                            ? const Icon(Icons.error_outline,
                                size: 58, color: PlegmaColors.red)
                            : Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text('$pct',
                                      style: const TextStyle(
                                          fontSize: 60,
                                          fontWeight: FontWeight.w200,
                                          color: PlegmaColors.cyan,
                                          letterSpacing: -2)),
                                  const Text('%',
                                      style: TextStyle(
                                          fontSize: 14,
                                          color: PlegmaColors.textDim,
                                          letterSpacing: 2)),
                                ],
                              ),
                  ],
                ),
              ),

              const SizedBox(height: 36),

              if (_concluido) ...[
                const Text('PROTEÇÃO ATIVADA',
                    style: TextStyle(
                        fontSize: 15, color: PlegmaColors.green,
                        letterSpacing: 3, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                const Text('Lattice Shield está ativo',
                    style: TextStyle(fontSize: 12, color: PlegmaColors.textDim)),
              ] else if (_erro) ...[
                const Text('FALHA NA ATIVAÇÃO',
                    style: TextStyle(
                        fontSize: 13, color: PlegmaColors.red, letterSpacing: 2)),
                if (_erroMsg != null) ...[
                  const SizedBox(height: 8),
                  Text(_erroMsg!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
                ],
              ] else ...[
                const Text('ATIVANDO LATTICE SHIELD',
                    style: TextStyle(
                        fontSize: 12, color: PlegmaColors.cyan, letterSpacing: 2.5)),
                const SizedBox(height: 10),
                Text(_faseAtual,
                    style: const TextStyle(
                        fontSize: 11, color: PlegmaColors.textDim, letterSpacing: 1)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// _SaldoStatusCard removido — informações de status integradas no _PaymentSelector

/*
class _SaldoStatusCard extends StatelessWidget {
  final Map<String, dynamic>? payInfo;
  const _SaldoStatusCard({required this.payInfo});

  @override
  Widget build(BuildContext context) {
    final ehValidador = payInfo?['eh_validador']    == true;
    final saldo       = (payInfo?['saldo_plg']       as num?)?.toDouble() ?? 0.0;
    final preco       = (payInfo?['preco_plg']       as num?)?.toDouble() ?? 1200.0;
    final saldoOk     = payInfo?['saldo_suficiente'] == true;
    final bloqueado   = !ehValidador && !saldoOk;

    final Color    cor;
    final IconData icone;
    final String   titulo;
    final String   subtitulo;

    if (ehValidador) {
      cor       = PlegmaColors.green;
      icone     = Icons.bolt;
      titulo    = 'Validador Ativo — Desconto da Mineração';
      subtitulo = 'O custo do Shield (≈ US\$ 12) será descontado automaticamente '
                  'das suas recompensas de mineração.';
    } else if (saldoOk) {
      cor       = PlegmaColors.amber;
      icone     = Icons.account_balance_wallet_outlined;
      titulo    = 'Saldo disponível — será debitado ao ativar';
      subtitulo = 'Serão debitados ${preco.toStringAsFixed(0)} PLG (≈ US\$ 12) '
                  'da sua carteira e enviados ao Aerarium.';
    } else {
      cor       = PlegmaColors.red;
      icone     = Icons.wallet_outlined;
      titulo    = 'Saldo PLG insuficiente para ativar';
      subtitulo = 'Necessário: ${preco.toStringAsFixed(0)} PLG (≈ US\$ 12)  '
                  '|  Atual: ${saldo.toStringAsFixed(0)} PLG';
    }

    return GestureDetector(
      onTap: bloqueado
          ? () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Ative o validador ou adquira PLG para continuar.'),
                backgroundColor: PlegmaColors.red,
                duration: Duration(seconds: 3),
              ),
            )
          : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        decoration: BoxDecoration(
          color          : cor.withValues(alpha: 0.07),
          borderRadius   : BorderRadius.circular(12),
          border         : Border.all(color: cor.withValues(alpha: 0.45), width: 1.5),
        ),
        child: Row(
          children: [
            Icon(icone, size: 24, color: cor),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(titulo,
                    style: TextStyle(
                      fontSize: 12, fontWeight: FontWeight.bold,
                      color: cor, letterSpacing: 0.3,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(subtitulo,
                    style: const TextStyle(
                      fontSize: 10, color: PlegmaColors.textDim, height: 1.4,
                    ),
                  ),
                  if (bloqueado) ...[
                    const SizedBox(height: 6),
                    Text('Toque para saber como resolver →',
                      style: TextStyle(
                        fontSize: 9, color: cor.withValues(alpha: 0.7),
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
*/
