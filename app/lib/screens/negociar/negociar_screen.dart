import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../services/storage_service.dart';
import '../../theme/plegma_theme.dart';

// Azul exchange — botão COMPRAR
const Color _kBuy  = Color(0xFF1E88E5);
const Color _kSell = Color(0xFFEF4444);

// ── Wrapper autônomo (nav legada / acesso direto) ────────────────────────────
class NegociarScreen extends StatefulWidget {
  const NegociarScreen({super.key});
  @override
  State<NegociarScreen> createState() => _NegociarScreenWrapState();
}

class _NegociarScreenWrapState extends State<NegociarScreen> {
  final _bodyKey = GlobalKey<_NegociarBodyState>();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        backgroundColor: PlegmaColors.bg,
        elevation      : 0,
        titleSpacing   : 16,
        title: Row(children: [
          const Text('NEGOCIAR',
            style: TextStyle(color: PlegmaColors.cyan, fontSize: 13,
                letterSpacing: 3, fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              border: Border.all(color: PlegmaColors.cyan.withOpacity(0.3)),
              borderRadius: BorderRadius.circular(3),
            ),
            child: Text('PLG / USDC',
              style: TextStyle(color: PlegmaColors.cyan.withOpacity(0.6),
                  fontSize: 9, letterSpacing: 2)),
          ),
        ]),
        actions: [
          IconButton(
            icon     : const Icon(Icons.refresh, color: PlegmaColors.textDim, size: 20),
            onPressed: () => _bodyKey.currentState?.refresh(),
          ),
        ],
      ),
      body: NegociarBody(key: _bodyKey),
    );
  }
}

// ── Corpo embeddable (usado como tab em WalletScreen) ────────────────────────
class NegociarBody extends StatefulWidget {
  const NegociarBody({super.key});
  @override
  State<NegociarBody> createState() => _NegociarBodyState();
}

class _NegociarBodyState extends State<NegociarBody>
    with AutomaticKeepAliveClientMixin {

  @override
  bool get wantKeepAlive => true;

  // ── Estado ──────────────────────────────────────────────────────────────
  bool   _isBuy       = true;
  double _pct         = 0.0;          // 0..1 slider
  bool   _slippage    = false;
  bool   _carregando  = true;

  Map<String, dynamic>? _cotacao;
  String? _address;
  Map<String, dynamic>? _ordemResult;
  bool   _enviando    = false;

  final _valorCtrl   = TextEditingController();
  final _polygonCtrl = TextEditingController();

  // ── Ciclo de vida ────────────────────────────────────────────────────────
  @override
  void initState() {
    super.initState();
    _carregar();
  }

  @override
  void dispose() {
    _valorCtrl.dispose();
    _polygonCtrl.dispose();
    super.dispose();
  }

  Future<void> _carregar() async {
    setState(() => _carregando = true);
    final r = await Future.wait([
      ApiService.getPoolCotacao(),
      StorageService.lerEndereco(),
    ]);
    if (!mounted) return;
    setState(() {
      _cotacao   = r[0] as Map<String, dynamic>?;
      _address   = r[1] as String?;
      _carregando = false;
    });
  }

  // ── Getters ──────────────────────────────────────────────────────────────
  double get _preco      => (_cotacao?['preco_inicial'] as num?)?.toDouble() ?? 0.10;
  double get _taxa       => (_cotacao?['taxa']          as num?)?.toDouble() ?? 10.0;
  double get _plgReserva => (_cotacao?['plg_reserva']   as num?)?.toDouble() ?? 0;
  double get _usdcSaldo  => (_cotacao?['usdc_saldo']    as num?)?.toDouble() ?? 0;
  bool   get _poolAtiva  => _cotacao?['disponivel'] == true;

  String get _moedaInput  => _isBuy  ? 'USDC' : 'PLG';
  String get _moedaOutput => _isBuy  ? 'PLG'  : 'USDC';

  double get _valorInput  => double.tryParse(_valorCtrl.text) ?? 0;
  double get _valorOutput => _isBuy
      ? (_taxa > 0 ? _valorInput * _taxa    : 0)
      : (_taxa > 0 ? _valorInput / _taxa    : 0);

  // ── Slider % ─────────────────────────────────────────────────────────────
  void _setPct(double v) {
    setState(() {
      _pct = v;
      // Para compra usa USDC disponível (simulado); para venda usa PLG reserva
      final base = _isBuy ? _usdcSaldo : _plgReserva;
      _valorCtrl.text = base > 0
          ? (base * v).toStringAsFixed(2)
          : '';
    });
  }

  // ── Ação ─────────────────────────────────────────────────────────────────
  Future<void> _executar() async {
    final valor = _valorInput;
    if (valor <= 0 || _address == null || _address!.isEmpty) return;
    if (!_isBuy && _polygonCtrl.text.trim().isEmpty) return;

    // Biometria obrigatória antes de qualquer transação
    AuthService.beginExternalAuth();
    final auth = await AuthService.authenticateBiometric(
      reason: _isBuy
          ? 'Confirme para comprar \$PLG'
          : 'Confirme para vender \$PLG',
    );
    if (!mounted) return;
    if (!auth) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content        : Text('✗ Autenticação necessária para transações'),
        backgroundColor: PlegmaColors.red,
      ));
      return;
    }

    setState(() { _enviando = true; _ordemResult = null; });

    Map<String, dynamic>? result;
    if (_isBuy) {
      result = await ApiService.comprarPlg(_address!, valor);
    } else {
      result = await ApiService.venderPlg(
        plgAddress: _address!,
        plgAmount: valor,
        polygonAddress: _polygonCtrl.text.trim(),
      );
    }
    if (!mounted) return;
    setState(() { _enviando = false; _ordemResult = result; });
  }

  void refresh() => _carregar();

  // ── Build ────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_carregando) {
      return const Center(child: CircularProgressIndicator(color: PlegmaColors.cyan));
    }
    if (_ordemResult != null && _ordemResult!['ok'] == true) {
      return _buildConfirmacao();
    }
    return _buildExchange();
  }

  // ── Layout principal exchange ─────────────────────────────────────────────
  Widget _buildExchange() {
    return Column(children: [
      // Preço atual
      _buildTickerBar(),
      // Conteúdo
      Expanded(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Formulário (esquerda)
            Expanded(child: _buildForm()),
            // Order book (direita)
            SizedBox(width: 150, child: _buildOrderBook()),
          ],
        ),
      ),
    ]);
  }

  // ── Ticker bar ───────────────────────────────────────────────────────────
  Widget _buildTickerBar() {
    return Container(
      padding  : const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color : PlegmaColors.bg2,
        border: const Border(bottom: BorderSide(color: PlegmaColors.border)),
      ),
      child: Row(children: [
        Text(
          _preco > 0 ? _preco.toStringAsFixed(4) : '--',
          style: TextStyle(
            fontSize: 18, fontWeight: FontWeight.w800,
            color: _isBuy ? _kBuy : _kSell,
            fontFamily: 'monospace',
          ),
        ),
        const SizedBox(width: 6),
        Text('USDC', style: TextStyle(
            fontSize: 10, color: PlegmaColors.textDim, letterSpacing: 1)),
        const Spacer(),
        _tickItem('POOL PLG', _plgReserva > 0 ? _plgReserva.toStringAsFixed(0) : '--'),
        const SizedBox(width: 14),
        _tickItem('POOL USDC', _usdcSaldo > 0 ? '\$${_usdcSaldo.toStringAsFixed(0)}' : '--'),
        const SizedBox(width: 14),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: _poolAtiva
                ? const Color(0xFF22C55E).withOpacity(0.1)
                : PlegmaColors.amber.withOpacity(0.1),
            borderRadius: BorderRadius.circular(3),
          ),
          child: Text(
            _poolAtiva ? 'ATIVA' : 'INATIVA',
            style: TextStyle(
              fontSize: 8, letterSpacing: 1.5,
              color: _poolAtiva ? const Color(0xFF22C55E) : PlegmaColors.amber,
            ),
          ),
        ),
      ]),
    );
  }

  Widget _tickItem(String l, String v) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(l, style: const TextStyle(fontSize: 8, color: PlegmaColors.textDim, letterSpacing: 1)),
      Text(v, style: const TextStyle(fontSize: 10, color: PlegmaColors.text, fontFamily: 'monospace')),
    ],
  );

  // ── Formulário ───────────────────────────────────────────────────────────
  Widget _buildForm() {
    final accentColor = _isBuy ? _kBuy : _kSell;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(14, 14, 8, 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

        // Toggle COMPRAR / VENDER
        Container(
          decoration: BoxDecoration(
            color: PlegmaColors.bg2,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: PlegmaColors.border),
          ),
          child: Row(children: [
            _toggleBtn('Comprar', true),
            _toggleBtn('Vender', false),
          ]),
        ),
        const SizedBox(height: 14),

        // Tipo: Mercado
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: PlegmaColors.bg2,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: PlegmaColors.border),
          ),
          child: Row(children: [
            const Icon(Icons.info_outline, size: 13, color: PlegmaColors.textDim),
            const SizedBox(width: 6),
            const Text('Mercado', style: TextStyle(fontSize: 12, color: PlegmaColors.text)),
            const Spacer(),
            Icon(Icons.arrow_drop_down, color: PlegmaColors.textDim.withOpacity(0.5)),
          ]),
        ),
        const SizedBox(height: 10),

        // Campo: Preço (desabilitado — mercado)
        _buildField(
          hint: 'Preço de Mercado',
          enabled: false,
          suffix: 'USDC',
          ctrl: null,
          value: _preco > 0 ? _preco.toStringAsFixed(6) : '',
        ),
        const SizedBox(height: 10),

        // Campo: Valor / Total
        _buildField(
          hint: _isBuy ? 'Total' : 'Valor',
          enabled: true,
          suffix: _moedaInput,
          ctrl: _valorCtrl,
          value: null,
          accentColor: accentColor,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 12),

        // Slider %
        _buildSlider(accentColor),
        const SizedBox(height: 10),

        // Slippage tolerance
        GestureDetector(
          onTap: () => setState(() => _slippage = !_slippage),
          child: Row(children: [
            SizedBox(
              width: 16, height: 16,
              child: Checkbox(
                value: _slippage,
                onChanged: (v) => setState(() => _slippage = v ?? false),
                activeColor: accentColor,
                side: BorderSide(color: PlegmaColors.border),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
            const SizedBox(width: 8),
            const Text('Tolerância ao desvio',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
          ]),
        ),
        const SizedBox(height: 14),

        // Info rows
        const Divider(color: PlegmaColors.border, height: 1),
        const SizedBox(height: 10),
        _buildInfoRow('Disponível',
          _isBuy
            ? (_usdcSaldo > 0 ? '${_usdcSaldo.toStringAsFixed(2)} USDC' : '0 USDC')
            : (_plgReserva > 0 ? '${_plgReserva.toStringAsFixed(0)} PLG' : '0 PLG'),
          highlight: true,
        ),
        _buildInfoRow(
          _isBuy ? 'Compra máx.' : 'Venda máx.',
          _isBuy
            ? (_usdcSaldo > 0 ? '${(_usdcSaldo * _taxa).toStringAsFixed(0)} PLG' : '0 PLG')
            : (_plgReserva > 0 ? '\$${(_plgReserva / _taxa).toStringAsFixed(4)} USDC' : '0 USDC'),
        ),
        _buildInfoRow('Taxa Est.',
          _taxa > 0 ? '${(0.001 * _valorInput).toStringAsFixed(4)} $_moedaInput' : '-- $_moedaInput'),

        // Preview output
        if (_valorOutput > 0) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: accentColor.withOpacity(0.06),
              border: Border.all(color: accentColor.withOpacity(0.25)),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Você recebe:', style: const TextStyle(
                    fontSize: 11, color: PlegmaColors.textDim)),
                Text('${_valorOutput.toStringAsFixed(4)} $_moedaOutput',
                  style: TextStyle(fontSize: 13,
                      color: accentColor, fontWeight: FontWeight.w700,
                      fontFamily: 'monospace')),
              ],
            ),
          ),
        ],

        // Campo endereço Polygon (venda)
        if (!_isBuy) ...[
          const SizedBox(height: 10),
          _buildField(
            hint: 'Seu endereço Polygon (0x...)',
            enabled: true,
            suffix: null,
            ctrl: _polygonCtrl,
            value: null,
            mono: true,
          ),
        ],
        const SizedBox(height: 16),

        // Botão ação
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: accentColor,
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            onPressed: (_enviando || !_poolAtiva) ? null : _executar,
            child: _enviando
                ? const SizedBox(height: 18, width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : Text(
                    _isBuy ? 'Comprar $_moedaOutput' : 'Vender $_moedaInput',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700,
                        letterSpacing: 1),
                  ),
          ),
        ),

        if (!_poolAtiva) ...[
          const SizedBox(height: 8),
          Text(
            _cotacao == null
                ? 'Servidor offline — verifique conexão.'
                : 'Pool ativada no encerramento da Genesis (Dia 30).',
            style: TextStyle(fontSize: 10, color: PlegmaColors.amber.withOpacity(0.8),
                height: 1.5),
            textAlign: TextAlign.center,
          ),
        ],
      ]),
    );
  }

  Widget _toggleBtn(String label, bool isBuy) {
    final active = _isBuy == isBuy;
    final color  = isBuy ? _kBuy : _kSell;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() {
          _isBuy = isBuy;
          _pct   = 0;
          _valorCtrl.clear();
          _ordemResult = null;
        }),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(vertical: 11),
          decoration: BoxDecoration(
            color: active ? color : Colors.transparent,
            borderRadius: BorderRadius.circular(7),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 1,
              color: active ? Colors.white : PlegmaColors.textDim,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildField({
    required String hint,
    required bool enabled,
    String? suffix,
    TextEditingController? ctrl,
    String? value,
    Color? accentColor,
    ValueChanged<String>? onChanged,
    bool mono = false,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: enabled ? PlegmaColors.bg2 : PlegmaColors.bg2.withOpacity(0.5),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: accentColor != null && enabled
              ? accentColor.withOpacity(0.4)
              : PlegmaColors.border,
        ),
      ),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: ctrl,
            enabled: enabled,
            keyboardType: ctrl != null && suffix != null
                ? const TextInputType.numberWithOptions(decimal: true)
                : TextInputType.text,
            style: TextStyle(
              color: enabled ? PlegmaColors.text : PlegmaColors.textDim,
              fontSize: 12,
              fontFamily: mono ? 'monospace' : null,
            ),
            decoration: InputDecoration(
              hintText: value?.isNotEmpty == true ? value : hint,
              hintStyle: TextStyle(
                color: value?.isNotEmpty == true
                    ? PlegmaColors.text.withOpacity(0.5)
                    : PlegmaColors.textDim,
                fontSize: 12,
              ),
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            ),
            onChanged: onChanged,
          ),
        ),
        if (suffix != null)
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Text(suffix,
              style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim,
                  letterSpacing: 1)),
          ),
      ]),
    );
  }

  Widget _buildSlider(Color accent) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [0.25, 0.5, 0.75, 1.0].map((v) =>
          GestureDetector(
            onTap: () => _setPct(v),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _pct == v ? accent.withOpacity(0.15) : Colors.transparent,
                border: Border.all(
                  color: _pct == v ? accent.withOpacity(0.5) : PlegmaColors.border,
                ),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                '${(v * 100).toInt()}%',
                style: TextStyle(
                  fontSize: 10, color: _pct == v ? accent : PlegmaColors.textDim,
                  fontWeight: _pct == v ? FontWeight.w700 : FontWeight.normal,
                ),
              ),
            ),
          )
        ).toList(),
      ),
      const SizedBox(height: 6),
      SliderTheme(
        data: SliderThemeData(
          trackHeight: 2,
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
          overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
          activeTrackColor: accent,
          inactiveTrackColor: PlegmaColors.border,
          thumbColor: accent,
          overlayColor: accent.withOpacity(0.15),
        ),
        child: Slider(
          value: _pct, min: 0, max: 1,
          divisions: 100,
          onChanged: _setPct,
        ),
      ),
    ]);
  }

  Widget _buildInfoRow(String label, String value, {bool highlight = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
          Text(value, style: TextStyle(
            fontSize: 10, fontFamily: 'monospace',
            color: highlight ? PlegmaColors.text : PlegmaColors.textDim,
          )),
        ],
      ),
    );
  }

  // ── Order Book ───────────────────────────────────────────────────────────
  Widget _buildOrderBook() {
    final p = _preco > 0 ? _preco : 0.10;
    // Gera 5 asks (acima) e 5 bids (abaixo) em torno do preço atual
    final asks = List.generate(5, (i) {
      final price = p * (1 + 0.001 * (5 - i));
      final vol   = _fakeVol(i, seed: 1);
      return _OBEntry(price: price, vol: vol, isBid: false);
    }).reversed.toList();

    final bids = List.generate(5, (i) {
      final price = p * (1 - 0.001 * (i + 1));
      final vol   = _fakeVol(i, seed: 2);
      return _OBEntry(price: price, vol: vol, isBid: true);
    });

    final maxVol = [...asks, ...bids].map((e) => e.vol).reduce(math.max);

    // Pressão
    final totalAsk = asks.fold(0.0, (s, e) => s + e.vol);
    final totalBid = bids.fold(0.0, (s, e) => s + e.vol);
    final bidPct   = totalBid / (totalAsk + totalBid);

    return Container(
      decoration: const BoxDecoration(
        border: Border(left: BorderSide(color: PlegmaColors.border)),
      ),
      child: Column(children: [
        // Header
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Preço\n(USDC)', style: TextStyle(
                  fontSize: 8, color: PlegmaColors.textDim, height: 1.4)),
              Text('Vol\n(PLG)', style: TextStyle(
                  fontSize: 8, color: PlegmaColors.textDim, height: 1.4),
                  textAlign: TextAlign.right),
            ],
          ),
        ),
        const Divider(height: 1, color: PlegmaColors.border),

        // Asks (sell — vermelho)
        ...asks.map((e) => _buildOBRow(e, maxVol)),

        // Preço atual
        Container(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
          child: Column(children: [
            Text(
              p.toStringAsFixed(4),
              style: TextStyle(
                fontSize: 16, fontWeight: FontWeight.w800,
                color: _isBuy ? _kBuy : _kSell,
                fontFamily: 'monospace',
              ),
            ),
          ]),
        ),

        // Bids (buy — azul/cyan)
        ...bids.map((e) => _buildOBRow(e, maxVol)),

        const Spacer(),

        // Barra pressão
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Column(children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('${(bidPct * 100).toStringAsFixed(1)}%',
                  style: const TextStyle(fontSize: 9, color: _kBuy)),
                Text('${((1 - bidPct) * 100).toStringAsFixed(1)}%',
                  style: const TextStyle(fontSize: 9, color: _kSell)),
              ],
            ),
            const SizedBox(height: 3),
            ClipRRect(
              borderRadius: BorderRadius.circular(2),
              child: Row(children: [
                Expanded(
                  flex: (bidPct * 100).round(),
                  child: Container(height: 4, color: _kBuy),
                ),
                Expanded(
                  flex: ((1 - bidPct) * 100).round(),
                  child: Container(height: 4, color: _kSell),
                ),
              ]),
            ),
          ]),
        ),
      ]),
    );
  }

  Widget _buildOBRow(_OBEntry e, double maxVol) {
    final color = e.isBid ? _kBuy : _kSell;
    final barW  = maxVol > 0 ? e.vol / maxVol : 0.0;
    return SizedBox(
      height: 22,
      child: Stack(children: [
        // Barra de volume (fundo)
        Positioned(
          right: 0, top: 0, bottom: 0,
          width: 130 * barW,
          child: Container(color: color.withOpacity(0.08)),
        ),
        // Preço e volume
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(e.price.toStringAsFixed(4),
                style: TextStyle(fontSize: 9, color: color, fontFamily: 'monospace')),
              Text(e.vol.toStringAsFixed(0),
                style: const TextStyle(fontSize: 9,
                    color: PlegmaColors.textDim, fontFamily: 'monospace')),
            ],
          ),
        ),
      ]),
    );
  }

  // Gera volume sintético baseado no índice + seed (determinístico por preço)
  double _fakeVol(int i, {required int seed}) {
    final base = (_preco > 0 ? _preco * 1000 : 100) * (1 + seed * 0.3);
    return base * (1 - i * 0.12) * (0.5 + (i * seed % 5) * 0.12);
  }

  // ── Confirmação ──────────────────────────────────────────────────────────
  Widget _buildConfirmacao() {
    final ordem = _ordemResult!;
    final isBuy = _isBuy;
    final accent = isBuy ? _kBuy : _kSell;

    return ListView(padding: const EdgeInsets.all(16), children: [
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: PlegmaColors.bg2,
          border: Border.all(color: accent.withOpacity(0.3)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 32, height: 32,
              decoration: BoxDecoration(
                color: accent.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.check, color: accent, size: 18),
            ),
            const SizedBox(width: 12),
            Text(
              isBuy ? 'Ordem de Compra Registrada' : 'Ordem de Venda Registrada',
              style: const TextStyle(color: PlegmaColors.text,
                  fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ]),
          const SizedBox(height: 20),
          if (isBuy) ...[
            _confRow('REF', _shortStr(ordem['ref_id'])),
            _confRow('Enviar', '\$${(ordem['usdc_amount'] as num?)?.toStringAsFixed(2) ?? '--'} USDC'),
            _confRow('Você recebe', '${(ordem['plg_estimado'] as num?)?.toStringAsFixed(2) ?? '--'} PLG',
                color: accent),
            _confRow('Rede', 'Polygon (MATIC)'),
            const SizedBox(height: 14),
            Text('Carteira destino',
                style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim,
                    letterSpacing: 1)),
            const SizedBox(height: 6),
            GestureDetector(
              onTap: () {
                Clipboard.setData(ClipboardData(
                    text: ordem['pool_address'] ?? ''));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Copiado'), duration: Duration(seconds: 2)));
              },
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: PlegmaColors.bg,
                  border: Border.all(color: accent.withOpacity(0.3)),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Row(children: [
                  Expanded(child: Text(
                    (ordem['pool_address'] as String?) ?? '--',
                    style: const TextStyle(color: PlegmaColors.text,
                        fontSize: 10, fontFamily: 'monospace'),
                  )),
                  const Icon(Icons.copy, size: 13, color: PlegmaColors.textDim),
                ]),
              ),
            ),
          ] else ...[
            _confRow('REF', _shortStr(ordem['ref_id'])),
            _confRow('PLG vendido',
                '${(ordem['plg_amount'] as num?)?.toStringAsFixed(2) ?? '--'} PLG'),
            _confRow('USDC estimado',
                '\$${(ordem['usdc_estimado'] as num?)?.toStringAsFixed(4) ?? '--'} USDC',
                color: accent),
            _confRow('Status', 'PENDENTE — até 24h', color: PlegmaColors.amber),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: PlegmaColors.textDim,
                side: const BorderSide(color: PlegmaColors.border),
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
              onPressed: () => setState(() => _ordemResult = null),
              child: Text(isBuy ? '← Nova Compra' : '← Nova Venda',
                  style: const TextStyle(fontSize: 11, letterSpacing: 1)),
            ),
          ),
        ]),
      ),
    ]);
  }

  Widget _confRow(String l, String v, {Color? color}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(l, style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
        Text(v, style: TextStyle(fontSize: 11, fontFamily: 'monospace',
            color: color ?? PlegmaColors.text)),
      ],
    ),
  );

  String _shortStr(dynamic v) {
    final s = (v as String?) ?? '';
    return s.length > 14 ? '${s.substring(0, 14)}…' : s;
  }
}

// ── Modelo order book ────────────────────────────────────────────────────────
class _OBEntry {
  final double price;
  final double vol;
  final bool   isBid;
  const _OBEntry({required this.price, required this.vol, required this.isBid});
}
