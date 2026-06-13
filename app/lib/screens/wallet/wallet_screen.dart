import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/wallet_provider.dart';
import '../../models/wallet_model.dart';
import '../../widgets/plegma_card.dart';
import '../../services/auth_service.dart';
import '../negociar/negociar_screen.dart';

// ── Formatadores globais ───────────────────────────────────────────────────────
String fmtPlg(double v)  => '${v.toStringAsFixed(2)} \$PLG';
String fmtPlgg(double v) => v.toStringAsFixed(2);
String fmtUsdt(double v) => '≈ \$${v.toStringAsFixed(2)}';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final wallet = context.watch<WalletProvider>();

    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        title: const Text('WALLET', style: TextStyle(letterSpacing: 3)),
        bottom: TabBar(
          controller          : _tabs,
          labelColor          : PlegmaColors.cyan,
          unselectedLabelColor: PlegmaColors.textDim,
          indicatorColor      : PlegmaColors.cyan,
          indicatorSize       : TabBarIndicatorSize.label,
          labelStyle          : const TextStyle(fontSize: 10, letterSpacing: 2),
          tabs                : const [
            Tab(text: 'SALDO'),
            Tab(text: 'VESTING'),
            Tab(text: 'EXTRATO'),
            Tab(text: 'NEGOCIAR'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children  : [
          _SaldoTab(wallet: wallet),
          _VestingTab(wallet: wallet),
          _ExtratoTab(wallet: wallet),
          const NegociarBody(),
        ],
      ),
    );
  }
}

// ── Aba Saldo ─────────────────────────────────────────────────────────────────
class _SaldoTab extends StatelessWidget {
  final WalletProvider wallet;
  const _SaldoTab({required this.wallet});

  @override
  Widget build(BuildContext context) {
    final w              = wallet.wallet;
    final histPlg        = wallet.precoHistorico;
    final plgPreco       = wallet.plgPreco;
    final plgVar         = wallet.plgVariacao;
    final plggPreco      = wallet.plggPreco;
    final plggFonte      = wallet.plggFonte;          // 'genesis' ou 'p2p'
    final plggSemVendas  = wallet.plggSemVendas;
    final plggVendaData  = wallet.plggUltimaVendaData;
    final corPlg         = plgVar >= 0 ? PlegmaColors.green : PlegmaColors.red;

    return ListView(
      padding : const EdgeInsets.all(16),
      children: [

        // ════════════════════════════════════════
        // CARD 1 — $PLG (mainnet, mineração R=G/N)
        // ════════════════════════════════════════
        PlegmaCard(
          topAccent: PlegmaColors.cyan,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PlegmaLabel('\$PLG · SALDO PRINCIPAL'),
              const SizedBox(height: 10),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    w != null ? fmtPlg(w.totalEstimado) : '-- \$PLG',
                    style: const TextStyle(
                      fontSize: 26, color: PlegmaColors.cyan,
                      fontWeight: FontWeight.bold, letterSpacing: 1,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    w != null ? fmtUsdt(w.totalUsdt) : '≈ --',
                    style: const TextStyle(fontSize: 13, color: PlegmaColors.textDim),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  _miniSaldo('DISPONÍVEL', w != null ? fmtPlg(w.disponivel)    : '--', PlegmaColors.green),
                  const SizedBox(width: 24),
                  _miniSaldo('VESTING',    w != null ? fmtPlg(w.vestingLocked) : '--', PlegmaColors.amber),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 10),

        // Cotação PLG/USDT
        PlegmaCard(
          topAccent: PlegmaColors.cyan,
          padding  : EdgeInsets.zero,
          child    : Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                child: Row(
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const PlegmaLabel('\$PLG / USDT'),
                        const SizedBox(height: 4),
                        Text(
                          '\$ ${plgPreco.toStringAsFixed(6)}',
                          style: const TextStyle(
                            fontSize: 20, color: PlegmaColors.cyan,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Row(children: [
                          Icon(plgVar >= 0 ? Icons.arrow_upward : Icons.arrow_downward,
                              color: corPlg, size: 11),
                          Text('${plgVar.toStringAsFixed(2)}%',
                              style: TextStyle(fontSize: 11, color: corPlg, letterSpacing: 1)),
                        ]),
                      ],
                    ),
                    const Spacer(),
                    _badge('PRÉ-LISTAGEM', PlegmaColors.amber),
                  ],
                ),
              ),
              if (histPlg.length >= 2)
                SizedBox(
                  height: 70,
                  child: LineChart(_miniChart(histPlg, corPlg)),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'MÍN: \$ ${histPlg.isNotEmpty ? histPlg.reduce((a, b) => a < b ? a : b).toStringAsFixed(6) : '--'}',
                      style: const TextStyle(fontSize: 9, color: PlegmaColors.red, letterSpacing: 1),
                    ),
                    Text(
                      'MÁX: \$ ${histPlg.isNotEmpty ? histPlg.reduce((a, b) => a > b ? a : b).toStringAsFixed(6) : '--'}',
                      style: const TextStyle(fontSize: 9, color: PlegmaColors.green, letterSpacing: 1),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // ════════════════════════════════════════
        // CARD 2 — PLG-G (sempre visível)
        // ════════════════════════════════════════
        PlegmaCard(
          topAccent: const Color(0xFFa78bfa),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const PlegmaLabel('PLG-G · GOVERNANÇA GENESIS'),
                  const Spacer(),
                  if (w != null && w.plggTotal > 0)
                    _badge(w.categoria, _categoriaColor(w.categoria)),
                ],
              ),

              // ── Selo Sócio Genesis ──
              if (w != null && w.socioGenesis) ...[
                const SizedBox(height: 10),
                _seloGenesisWidget(w),
              ],

              const SizedBox(height: 10),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    w != null && w.plggTotal > 0
                        ? '${fmtPlgg(w.plggTotal)} PLG-G'
                        : '0.00 PLG-G',
                    style: TextStyle(
                      fontSize: 26,
                      color: w != null && w.plggTotal > 0
                          ? const Color(0xFFa78bfa)
                          : PlegmaColors.textDim,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    w != null && w.plggTotal > 0
                        ? '≈ \$${(w.plggTotal * plggPreco).toStringAsFixed(2)}'
                        : '≈ \$0.00',
                    style: const TextStyle(fontSize: 13, color: PlegmaColors.textDim),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              if (w != null && w.plggTotal > 0) ...[
                Row(
                  children: [
                    _miniSaldo('BLOQUEADO',  fmtPlgg(w.plggLocked),    PlegmaColors.red),
                    const SizedBox(width: 24),
                    _miniSaldo('DISPONÍVEL', fmtPlgg(w.plggAvailable), PlegmaColors.green),
                    const SizedBox(width: 24),
                    _miniSaldo('BOOST', '${w.boostMineracao}×',        PlegmaColors.amber),
                  ],
                ),
                if (w.plggUnlockDate != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Unlock: ${w.plggUnlockDate}',
                    style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim),
                  ),
                ],
              ] else ...[
                Text(
                  'Adquira PLG-G na Reserva Genesis para\nparticipação na governança da rede.',
                  style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim, height: 1.5),
                ),
              ],
            ],
          ),
        ),

        const SizedBox(height: 10),

        // Cotação PLG-G — preço definido exclusivamente pelo Sócio vendedor
        PlegmaCard(
          topAccent: const Color(0xFFa78bfa),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      PlegmaLabel(plggSemVendas
                          ? 'PLG-G / USDC · PREÇO GENESIS'
                          : 'PLG-G / USDC · ÚLTIMA VENDA P2P'),
                      const SizedBox(height: 4),
                      Text(
                        '\$ ${plggPreco.toStringAsFixed(4)}',
                        style: const TextStyle(
                          fontSize: 20,
                          color: Color(0xFFa78bfa),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const Spacer(),
                  _badge(
                    plggFonte == 'p2p' ? 'P2P REAL' : 'EMISSÃO',
                    const Color(0xFFa78bfa),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              // Linha descritiva: fonte do preço
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFFa78bfa).withValues(alpha: 0.07),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFa78bfa).withValues(alpha: 0.25)),
                ),
                child: Row(
                  children: [
                    Icon(
                      plggSemVendas ? Icons.info_outline : Icons.verified_user_outlined,
                      color: const Color(0xFFa78bfa),
                      size: 13,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        plggSemVendas
                            ? 'Preço de emissão Genesis. Mercado P2P ativo pós-lançamento.\nO valor será determinado exclusivamente pelo Sócio vendedor.'
                            : 'Último preço definido pelo Sócio vendedor.${plggVendaData != null ? '\nRegistrado em: $plggVendaData' : ''}',
                        style: const TextStyle(
                          fontSize  : 10,
                          color     : PlegmaColors.textDim,
                          height    : 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),

        // ── Botões de ação ──
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ElevatedButton.icon(
              onPressed : () => _showReceberSheet(context),
              icon      : const Icon(Icons.qr_code, size: 15),
              label     : const Text('RECEBER'),
              style     : ElevatedButton.styleFrom(
                backgroundColor: PlegmaColors.green.withValues(alpha: 0.12),
                foregroundColor: PlegmaColors.green,
                side: const BorderSide(color: PlegmaColors.green, width: 0.8),
              ),
            ),
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed : () => _showEnviarPlgSheet(context),
              icon      : const Icon(Icons.send, size: 15),
              label     : const Text('ENVIAR \$PLG'),
              style     : ElevatedButton.styleFrom(
                backgroundColor: PlegmaColors.cyan.withValues(alpha: 0.12),
                foregroundColor: PlegmaColors.cyan,
                side: const BorderSide(color: PlegmaColors.cyan, width: 0.8),
              ),
            ),
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed : () => _showEnviarPlggSheet(context),
              icon      : const Icon(Icons.account_balance_wallet, size: 15),
              label     : const Text('ENVIAR PLG-G'),
              style     : ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFa78bfa).withValues(alpha: 0.12),
                foregroundColor: const Color(0xFFa78bfa),
                side: const BorderSide(color: Color(0xFFa78bfa), width: 0.8),
              ),
            ),
          ],
        ),

        // ── Card: Oferta P2P recebida ──
        if (wallet.ofertaRecebida != null) ...[
          const SizedBox(height: 16),
          _OfertaRecebidaCard(
            oferta: wallet.ofertaRecebida!,
            wallet: wallet,
          ),
        ],

        const SizedBox(height: 24),
      ],
    );
  }

  // ── Gráfico mini ──────────────────────────────────────────────────────────
  LineChartData _miniChart(List<double> hist, Color cor) => LineChartData(
    gridData    : const FlGridData(show: false),
    titlesData  : const FlTitlesData(show: false),
    borderData  : FlBorderData(show: false),
    lineBarsData: [
      LineChartBarData(
        spots       : hist.asMap().entries
            .map((e) => FlSpot(e.key.toDouble(), e.value))
            .toList(),
        isCurved    : true,
        color       : cor,
        barWidth    : 1.5,
        dotData     : const FlDotData(show: false),
        belowBarData: BarAreaData(show: true, color: cor.withValues(alpha: 0.08)),
      ),
    ],
  );

  // ── Helpers visuais ───────────────────────────────────────────────────────
  Color _categoriaColor(String cat) {
    switch (cat) {
      case 'MASTER':    return PlegmaColors.cyan;
      case 'SENTINELA': return const Color(0xFFa78bfa);
      default:          return PlegmaColors.textDim;
    }
  }

  // ── Selo Sócio Genesis ────────────────────────────────────────────────────
  Widget _seloGenesisWidget(WalletModel wm) {
    final ativo   = wm.seloGenesisAtivo;
    final perdido = wm.statusGenesisPerdido;

    if (perdido) {
      // Selo perdido — exibe aviso cinza
      return Container(
        padding   : const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color       : PlegmaColors.textDim.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(8),
          border      : Border.all(color: PlegmaColors.textDim.withValues(alpha: 0.2)),
        ),
        child: Row(
          children: [
            const Icon(Icons.workspace_premium, color: PlegmaColors.textDim, size: 16),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('SÓCIO GENESIS — SELO PERDIDO',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.textDim,
                          letterSpacing: 1.5, fontWeight: FontWeight.bold)),
                  SizedBox(height: 2),
                  Text('Saldo PLG-G zerado. O selo não se recupera mesmo com nova aquisição.',
                      style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, height: 1.4)),
                ],
              ),
            ),
          ],
        ),
      );
    }

    if (ativo) {
      // Selo ativo — exibe com destaque dourado
      return Container(
        padding   : const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              const Color(0xFFFFD700).withValues(alpha: 0.10),
              const Color(0xFFa78bfa).withValues(alpha: 0.08),
            ],
          ),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFFFFD700).withValues(alpha: 0.45)),
        ),
        child: Row(
          children: [
            const Icon(Icons.workspace_premium, color: Color(0xFFFFD700), size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('SÓCIO GENESIS',
                      style: TextStyle(fontSize: 10, color: Color(0xFFFFD700),
                          letterSpacing: 2.5, fontWeight: FontWeight.bold)),
                  SizedBox(height: 3),
                  Text(
                    'Único e intransferível · Não reemitido em edições futuras\n'
                    'O selo é pessoal. A governança viaja com o token.',
                    style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, height: 1.5),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }

    return const SizedBox.shrink();
  }

  Widget _badge(String label, Color cor) => Container(
    padding   : const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(
      color       : cor.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(4),
      border      : Border.all(color: cor.withValues(alpha: 0.4)),
    ),
    child: Text(label, style: TextStyle(
      fontSize: 8, color: cor, fontWeight: FontWeight.bold, letterSpacing: 1,
    )),
  );

  Widget _miniSaldo(String label, String valor, Color cor) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(
        fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1,
      )),
      const SizedBox(height: 2),
      Text(valor, style: TextStyle(
        fontSize: 12, color: cor, fontWeight: FontWeight.bold,
      )),
    ],
  );

  // ── Modal: Receber $PLG ──────────────────────────────────────────────────
  void _showReceberSheet(BuildContext context) {
    final w = wallet.wallet;
    showModalBottomSheet(
      context           : context,
      isScrollControlled: true,
      useSafeArea       : true,
      backgroundColor   : PlegmaColors.bg2,
      shape             : const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 36, height: 4,
              margin: const EdgeInsets.only(bottom: 20),
              decoration: BoxDecoration(
                color: PlegmaColors.border,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Text('RECEBER \$PLG', style: TextStyle(
              fontSize: 13, color: PlegmaColors.green,
              letterSpacing: 3, fontWeight: FontWeight.bold,
            )),
            const SizedBox(height: 20),
            Container(
              padding   : const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color       : Colors.white,
                borderRadius: BorderRadius.circular(10),
              ),
              child: QrImageView(
                data: w?.plgAddress ?? '',
                version: QrVersions.auto,
                size: 200,
                backgroundColor: Colors.white,
                eyeStyle: const QrEyeStyle(
                  eyeShape: QrEyeShape.square,
                  color   : Colors.black,
                ),
                dataModuleStyle: const QrDataModuleStyle(
                  dataModuleShape: QrDataModuleShape.square,
                  color          : Colors.black,
                ),
              ),
            ),
            const SizedBox(height: 16),
            SelectableText(
              w?.plgAddress ?? '--',
              style: const TextStyle(
                fontFamily: 'SpaceMono',
                fontSize  : 10,
                color     : PlegmaColors.textDim,
                letterSpacing: 1,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  side   : const BorderSide(color: PlegmaColors.green),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                icon : const Icon(Icons.copy, size: 14, color: PlegmaColors.green),
                label: const Text(
                  'COPIAR ENDEREÇO',
                  style: TextStyle(
                    color      : PlegmaColors.green,
                    fontSize   : 10,
                    letterSpacing: 1.5,
                  ),
                ),
                onPressed: () {
                  if (w?.plgAddress != null) {
                    Clipboard.setData(ClipboardData(text: w!.plgAddress));
                    ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                      content        : Text('Endereço copiado para a área de transferência'),
                      duration       : Duration(seconds: 2),
                      backgroundColor: PlegmaColors.bg2,
                    ));
                  }
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Modal: Enviar $PLG ────────────────────────────────────────────────────
  void _showEnviarPlgSheet(BuildContext context) {
    final destCtrl   = TextEditingController();
    final amountCtrl = TextEditingController();
    final w          = wallet.wallet;

    final pesoVoto      = w?.pesoVoto ?? 1.0;
    final limiteEfetivo = 500000.0 * pesoVoto;

    showModalBottomSheet(
      context            : context,
      isScrollControlled : true,
      useSafeArea        : true,
      backgroundColor    : PlegmaColors.bg2,
      shape              : const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final digitado   = double.tryParse(amountCtrl.text) ?? 0;
          final whaleAlert = digitado > limiteEfetivo && digitado > 0;

          return DraggableScrollableSheet(
            expand          : false,
            initialChildSize: 0.55,
            minChildSize    : 0.4,
            maxChildSize    : 0.9,
            builder: (ctx, scrollCtrl) => SingleChildScrollView(
              controller: scrollCtrl,
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
                left: 20, right: 20, top: 8,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Handle
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
                  const Text('ENVIAR \$PLG', style: TextStyle(
                    fontSize: 13, color: PlegmaColors.cyan,
                    letterSpacing: 3, fontWeight: FontWeight.bold,
                  )),
                  const SizedBox(height: 16),
                  TextField(
                    controller        : destCtrl,
                    style             : const TextStyle(color: PlegmaColors.cyan, fontSize: 12),
                    textCapitalization: TextCapitalization.characters,
                    decoration        : InputDecoration(
                      labelText: 'Endereço PLG Destino',
                      suffixIcon: IconButton(
                        icon   : const Icon(Icons.qr_code_scanner, size: 20, color: PlegmaColors.cyan),
                        tooltip: 'Ler QR code',
                        onPressed: () async {
                          final resultado = await Navigator.push<String>(
                            ctx,
                            MaterialPageRoute(
                              fullscreenDialog: true,
                              builder: (_) => const _PlgQrScannerPage(),
                            ),
                          );
                          if (resultado != null && resultado.isNotEmpty) {
                            destCtrl.text = resultado.toUpperCase();
                          }
                        },
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller  : amountCtrl,
                    style       : const TextStyle(color: PlegmaColors.text, fontSize: 14),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration  : InputDecoration(
                      labelText : 'Valor (\$PLG)',
                      helperText: 'Limite diário: ${_fmtLimite(limiteEfetivo)} \$PLG'
                          '${pesoVoto > 1.0 ? ' (peso ${pesoVoto.toStringAsFixed(2)}×)' : ''}',
                      helperStyle: const TextStyle(fontSize: 10, color: PlegmaColors.textDim),
                    ),
                    onChanged: (_) => setModalState(() {}),
                  ),
                  if (whaleAlert) ...[
                    const SizedBox(height: 12),
                    _avisoBox(
                      icone : Icons.timer,
                      cor   : PlegmaColors.amber,
                      titulo: 'WHALE DUMP DELAY',
                      corpo : 'Transferências superiores a ${_fmtLimite(limiteEfetivo)} \$PLG '
                          'em 24h são automaticamente fragmentadas pelo protocolo. '
                          'O valor será liquidado em lotes ao longo de 24h para preservar '
                          'a liquidez da rede.',
                    ),
                  ],
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: () async {
                        final dest   = destCtrl.text.trim().toUpperCase();
                        final amount = double.tryParse(amountCtrl.text) ?? 0;
                        if (dest.isEmpty || amount <= 0) return;
                        AuthService.beginExternalAuth();
                        final auth = await AuthService.authenticateBiometric(
                          reason: 'Confirme para enviar \$PLG',
                        );
                        if (!ctx.mounted) return;
                        if (!auth) {
                          ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                            content        : Text('✗ Autenticação necessária'),
                            backgroundColor: PlegmaColors.red,
                          ));
                          return;
                        }
                        final result = await wallet.transferir(
                          destinatario: dest, amount: amount,
                        );
                        if (!ctx.mounted) return;
                        Navigator.pop(ctx);
                        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
                          content: Text(result?['ok'] == true
                              ? '✓ Enviado com sucesso'
                              : '✗ ${result?['erro'] ?? 'Erro'}'),
                          backgroundColor: result?['ok'] == true
                              ? PlegmaColors.green : PlegmaColors.red,
                        ));
                      },
                      child: const Text('ASSINAR E ENVIAR'),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  String _fmtLimite(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)}M';
    if (v >= 1000)    return '${(v / 1000).toStringAsFixed(0)}K';
    return v.toStringAsFixed(0);
  }

  // ── Modal: Enviar PLG-G — venda P2P ──────────────────────────────────────
  void _showEnviarPlggSheet(BuildContext context) {
    final destCtrl   = TextEditingController();
    final amountCtrl = TextEditingController();
    final precoCtrl  = TextEditingController();
    final w              = wallet.wallet;
    final plggPreco      = wallet.plggPreco;
    final plggSemVendas  = wallet.plggSemVendas;
    final plggVendaData  = wallet.plggUltimaVendaData;

    // Pré-preenche com último preço de referência
    precoCtrl.text = plggPreco.toStringAsFixed(4);

    showModalBottomSheet(
      context            : context,
      isScrollControlled : true,
      useSafeArea        : true,
      backgroundColor    : PlegmaColors.bg2,
      shape              : const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final qtd   = double.tryParse(amountCtrl.text) ?? 0;
          final preco = double.tryParse(precoCtrl.text)  ?? 0;
          final total = qtd * preco;

          return DraggableScrollableSheet(
            expand          : false,
            initialChildSize: 0.85,
            minChildSize    : 0.5,
            maxChildSize    : 0.95,
            builder: (ctx, scrollCtrl) => SingleChildScrollView(
              controller: scrollCtrl,
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
                left: 20, right: 20, top: 8,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Handle
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

                  // Título + disponível
                  Row(
                    children: [
                      const Text('OFERTA P2P · PLG-G', style: TextStyle(
                        fontSize: 13, color: Color(0xFFa78bfa),
                        letterSpacing: 2.5, fontWeight: FontWeight.bold,
                      )),
                      const Spacer(),
                      Text(
                        'Disp: ${w != null ? fmtPlgg(w.plggAvailable) : "0.00"} PLG-G',
                        style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),

                  // ── Avisos ──
                  if (w != null && w.plggLocked > 0)
                    _avisoBox(
                      icone : Icons.lock_clock,
                      cor   : PlegmaColors.red,
                      titulo: 'LOCKUP ATIVO',
                      corpo : 'Você possui ${fmtPlgg(w.plggLocked)} PLG-G bloqueados até '
                          '${w.plggUnlockDate ?? "Dia 31 da Genesis"}. '
                          'Apenas ${fmtPlgg(w.plggAvailable)} PLG-G disponíveis.',
                    ),

                  _avisoBox(
                    icone : Icons.storefront_outlined,
                    cor   : const Color(0xFFa78bfa),
                    titulo: 'VENDA P2P DIRETA',
                    corpo : 'Você define o endereço do comprador e o preço em USDC. '
                        'O comprador recebe uma notificação e pode aceitar ou rejeitar a oferta. '
                        'O PLG-G só é transferido após a confirmação — e somente se o comprador '
                        'tiver saldo USDC suficiente.',
                  ),

                  _avisoBox(
                    icone : Icons.how_to_vote,
                    cor   : PlegmaColors.amber,
                    titulo: 'TRANSFERÊNCIA DE GOVERNANÇA',
                    corpo : 'Ao transferir PLG-G você transfere peso de voto e '
                        'posição de governança ao destinatário.',
                  ),

                  _avisoBox(
                    icone : Icons.price_change,
                    cor   : const Color(0xFFa78bfa),
                    titulo: 'REFERÊNCIA DE PREÇO',
                    corpo : plggSemVendas
                        ? 'Preço de emissão Genesis: \$0.1000 USDC por PLG-G.'
                        : 'Última venda P2P: \$${plggPreco.toStringAsFixed(4)} USDC'
                          '${plggVendaData != null ? " · $plggVendaData" : ""}.',
                  ),

                  _avisoBox(
                    icone : Icons.warning_amber_rounded,
                    cor   : PlegmaColors.red,
                    titulo: 'TRANSAÇÃO IRREVERSÍVEL',
                    corpo : 'Registrada permanentemente na DAG com Dilithium3. '
                        'Verifique endereço e valores com atenção.',
                  ),

                  const SizedBox(height: 4),

                  // ── Inputs ──
                  TextField(
                    controller        : destCtrl,
                    style             : const TextStyle(color: Color(0xFFa78bfa), fontSize: 12),
                    decoration        : const InputDecoration(
                      labelText  : 'Endereço PLG do Comprador',
                      labelStyle : TextStyle(color: Color(0xFFa78bfa)),
                      focusedBorder: UnderlineInputBorder(
                        borderSide: BorderSide(color: Color(0xFFa78bfa)),
                      ),
                    ),
                    textCapitalization: TextCapitalization.characters,
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        flex: 5,
                        child: TextField(
                          controller  : amountCtrl,
                          style       : const TextStyle(color: PlegmaColors.text, fontSize: 14),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration  : InputDecoration(
                            labelText : 'Quantidade (PLG-G)',
                            helperText: w != null && w.plggAvailable > 0
                                ? 'Máx: ${fmtPlgg(w.plggAvailable)}'
                                : 'Sem PLG-G disponível',
                            helperStyle: TextStyle(
                              fontSize: 10,
                              color: w != null && w.plggAvailable > 0
                                  ? PlegmaColors.textDim : PlegmaColors.red,
                            ),
                          ),
                          onChanged: (_) => setModalState(() {}),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 4,
                        child: TextField(
                          controller  : precoCtrl,
                          style       : const TextStyle(color: PlegmaColors.green, fontSize: 14),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration  : const InputDecoration(
                            labelText  : 'Preço (USDC)',
                            labelStyle : TextStyle(color: PlegmaColors.green),
                            prefixText : '\$ ',
                            prefixStyle: TextStyle(color: PlegmaColors.green),
                            helperText : 'por PLG-G',
                            helperStyle: TextStyle(fontSize: 10, color: PlegmaColors.textDim),
                            focusedBorder: UnderlineInputBorder(
                              borderSide: BorderSide(color: PlegmaColors.green),
                            ),
                          ),
                          onChanged: (_) => setModalState(() {}),
                        ),
                      ),
                    ],
                  ),

                  // ── Resumo da oferta ──
                  if (qtd > 0 && preco > 0) ...[
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFa78bfa).withValues(alpha: 0.07),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFa78bfa).withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('TOTAL DA OFERTA', style: TextStyle(
                                fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5,
                              )),
                              const SizedBox(height: 4),
                              Text(
                                '${fmtPlgg(qtd)} PLG-G',
                                style: const TextStyle(
                                  fontSize: 13, color: Color(0xFFa78bfa),
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text('VALOR USDC', style: TextStyle(
                                fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5,
                              )),
                              const SizedBox(height: 4),
                              Text(
                                '\$ ${total.toStringAsFixed(2)}',
                                style: const TextStyle(
                                  fontSize: 13, color: PlegmaColors.green,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],

                  const SizedBox(height: 16),

                  // ── Botão enviar oferta ──
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: (w != null && w.plggAvailable > 0)
                          ? () async {
                              final dest  = destCtrl.text.trim().toUpperCase();
                              final qtdV  = double.tryParse(amountCtrl.text) ?? 0;
                              final precoV= double.tryParse(precoCtrl.text)  ?? 0;
                              if (dest.isEmpty || qtdV <= 0 || precoV <= 0) {
                                ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                                  content: Text('Preencha endereço, quantidade e preço'),
                                  backgroundColor: PlegmaColors.amber,
                                ));
                                return;
                              }
                              if (w != null && qtdV > w.plggAvailable) { // ignore: unnecessary_null_comparison // ignore: unnecessary_null_comparison
                                ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                                  content: Text('Saldo PLG-G disponível insuficiente'),
                                  backgroundColor: PlegmaColors.red,
                                ));
                                return;
                              }
                              AuthService.beginExternalAuth();
                              final auth = await AuthService.authenticateBiometric(
                                reason: 'Confirme para enviar oferta PLG-G',
                              );
                              if (!ctx.mounted) return;
                              if (!auth) {
                                ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                                  content        : Text('✗ Autenticação necessária'),
                                  backgroundColor: PlegmaColors.red,
                                ));
                                return;
                              }
                              final result = await wallet.criarOfertaPlgg(
                                comprador     : dest,
                                amountPlgg    : qtdV,
                                precoUnitario : precoV,
                              );
                              if (!ctx.mounted) return;
                              Navigator.pop(ctx);
                              ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
                                content: Text(result?['ok'] == true
                                    ? '✓ Oferta enviada — aguardando resposta do comprador'
                                    : '✗ ${result?['erro'] ?? 'Erro ao enviar oferta'}'),
                                backgroundColor: result?['ok'] == true
                                    ? PlegmaColors.green : PlegmaColors.red,
                              ));
                            }
                          : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFa78bfa).withValues(alpha: 0.15),
                        foregroundColor: const Color(0xFFa78bfa),
                        side           : const BorderSide(color: Color(0xFFa78bfa), width: 0.8),
                        disabledBackgroundColor: PlegmaColors.border,
                        disabledForegroundColor: PlegmaColors.textDim,
                      ),
                      child: const Text('ASSINAR E ENVIAR OFERTA'),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  // ── Caixa de aviso padronizada ────────────────────────────────────────────
  Widget _avisoBox({
    required IconData icone,
    required Color    cor,
    required String   titulo,
    required String   corpo,
  }) =>
      Container(
        margin    : const EdgeInsets.only(bottom: 10),
        padding   : const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color       : cor.withValues(alpha: 0.07),
          borderRadius: BorderRadius.circular(8),
          border      : Border.all(color: cor.withValues(alpha: 0.35)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icone, color: cor, size: 16),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(titulo, style: TextStyle(
                    fontSize: 9, color: cor,
                    fontWeight: FontWeight.bold, letterSpacing: 1.5,
                  )),
                  const SizedBox(height: 4),
                  Text(corpo, style: const TextStyle(
                    fontSize: 11, color: PlegmaColors.textDim, height: 1.5,
                  )),
                ],
              ),
            ),
          ],
        ),
      );
}

// ── Card: Oferta P2P recebida ─────────────────────────────────────────────────
class _OfertaRecebidaCard extends StatefulWidget {
  final OfertaP2P      oferta;
  final WalletProvider wallet;
  const _OfertaRecebidaCard({required this.oferta, required this.wallet});

  @override
  State<_OfertaRecebidaCard> createState() => _OfertaRecebidaCardState();
}

class _OfertaRecebidaCardState extends State<_OfertaRecebidaCard> {
  bool _processando = false;

  Future<void> _responder(bool aceitar) async {
    setState(() => _processando = true);
    final result = await widget.wallet.responderOferta(
      ofertaId: widget.oferta.ofertaId,
      aceitar : aceitar,
    );
    if (!mounted) return;
    setState(() => _processando = false);
    final msg = aceitar
        ? (result?['ok'] == true
            ? '✓ Compra confirmada — PLG-G recebido'
            : '✗ ${result?['erro'] ?? 'Saldo USDC insuficiente'}')
        : '✓ Oferta rejeitada';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: aceitar && result?['ok'] == true
          ? PlegmaColors.green
          : aceitar ? PlegmaColors.red : PlegmaColors.textDim,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final o = widget.oferta;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFa78bfa).withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFa78bfa).withValues(alpha: 0.45), width: 1.2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8, height: 8,
                decoration: BoxDecoration(
                  color: const Color(0xFFa78bfa),
                  shape: BoxShape.circle,
                  boxShadow: [BoxShadow(color: const Color(0xFFa78bfa).withValues(alpha: 0.5), blurRadius: 4)],
                ),
              ),
              const SizedBox(width: 8),
              const Text('OFERTA P2P RECEBIDA', style: TextStyle(
                fontSize: 10, color: Color(0xFFa78bfa),
                letterSpacing: 2, fontWeight: FontWeight.bold,
              )),
              const Spacer(),
              Text('Exp: ${o.expiracao}', style: const TextStyle(
                fontSize: 9, color: PlegmaColors.textDim,
              )),
            ],
          ),
          const SizedBox(height: 12),
          // Vendedor
          Text(
            'De: ${o.vendedor.length > 16 ? '${o.vendedor.substring(0, 8)}...${o.vendedor.substring(o.vendedor.length - 6)}' : o.vendedor}',
            style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim),
          ),
          const SizedBox(height: 10),
          // Detalhes da oferta
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('QUANTIDADE', style: TextStyle(
                      fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5,
                    )),
                    const SizedBox(height: 3),
                    Text('${o.amountPlgg.toStringAsFixed(2)} PLG-G', style: const TextStyle(
                      fontSize: 15, color: Color(0xFFa78bfa), fontWeight: FontWeight.bold,
                    )),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    const Text('PREÇO / PLG-G', style: TextStyle(
                      fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5,
                    )),
                    const SizedBox(height: 3),
                    Text('\$ ${o.precoUnitario.toStringAsFixed(4)}', style: const TextStyle(
                      fontSize: 13, color: PlegmaColors.green, fontWeight: FontWeight.bold,
                    )),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text('TOTAL USDC', style: TextStyle(
                      fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1.5,
                    )),
                    const SizedBox(height: 3),
                    Text('\$ ${o.totalUsdc.toStringAsFixed(2)}', style: const TextStyle(
                      fontSize: 15, color: PlegmaColors.green, fontWeight: FontWeight.bold,
                    )),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // Aviso USDC
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: PlegmaColors.amber.withValues(alpha: 0.07),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: PlegmaColors.amber.withValues(alpha: 0.3)),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: PlegmaColors.amber, size: 12),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Ao aceitar, \$USDC será debitado da sua carteira automaticamente. '
                    'A transação falhará se o saldo for insuficiente.',
                    style: TextStyle(fontSize: 10, color: PlegmaColors.textDim, height: 1.4),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          // Botões aceitar/rejeitar
          _processando
              ? const Center(child: SizedBox(
                  width: 24, height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2, color: Color(0xFFa78bfa),
                  ),
                ))
              : Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => _responder(false),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: PlegmaColors.red,
                          side: const BorderSide(color: PlegmaColors.red, width: 0.8),
                        ),
                        child: const Text('REJEITAR', style: TextStyle(fontSize: 11)),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 2,
                      child: ElevatedButton(
                        onPressed: () => _responder(true),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFFa78bfa).withValues(alpha: 0.15),
                          foregroundColor: const Color(0xFFa78bfa),
                          side: const BorderSide(color: Color(0xFFa78bfa), width: 0.8),
                        ),
                        child: const Text('ACEITAR E PAGAR', style: TextStyle(fontSize: 11)),
                      ),
                    ),
                  ],
                ),
        ],
      ),
    );
  }
}

// ── Aba Vesting ───────────────────────────────────────────────────────────────
class _VestingTab extends StatefulWidget {
  final WalletProvider wallet;
  const _VestingTab({required this.wallet});

  @override
  State<_VestingTab> createState() => _VestingTabState();
}

class _VestingTabState extends State<_VestingTab> {
  @override
  void initState() {
    super.initState();
    widget.wallet.fetchVesting();
  }

  @override
  Widget build(BuildContext context) {
    final vestings = widget.wallet.vestings;
    if (vestings.isEmpty) {
      return const Center(
        child: Text('Nenhum vesting pendente',
            style: TextStyle(color: PlegmaColors.textDim)),
      );
    }
    return ListView.separated(
      padding         : const EdgeInsets.all(16),
      itemCount       : vestings.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder     : (_, i) {
        final v   = vestings[i];
        final cor = v.daysRemaining <= 3
            ? PlegmaColors.green
            : v.daysRemaining <= 10
                ? PlegmaColors.amber
                : PlegmaColors.textDim;
        return PlegmaCard(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(fmtPlg(v.amount), style: const TextStyle(
                      fontSize: 15, color: PlegmaColors.text,
                      fontWeight: FontWeight.bold,
                    )),
                    const SizedBox(height: 4),
                    Text('${v.pool} · ${v.releaseDate}', style: const TextStyle(
                      fontSize: 10, color: PlegmaColors.textDim,
                    )),
                  ],
                ),
              ),
              Container(
                padding   : const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color       : cor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                  border      : Border.all(color: cor.withValues(alpha: 0.4)),
                ),
                child: Text('${v.daysRemaining}d', style: TextStyle(
                  fontSize: 13, color: cor, fontWeight: FontWeight.bold,
                )),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── Aba Extrato ───────────────────────────────────────────────────────────────
class _ExtratoTab extends StatefulWidget {
  final WalletProvider wallet;
  const _ExtratoTab({required this.wallet});

  @override
  State<_ExtratoTab> createState() => _ExtratoTabState();
}

class _ExtratoTabState extends State<_ExtratoTab> {
  String? _filtro;

  @override
  void initState() {
    super.initState();
    widget.wallet.fetchExtrato();
  }

  @override
  Widget build(BuildContext context) {
    final txs = widget.wallet.extrato;
    return Column(
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding        : const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              _filtroChip('TODAS',    null),
              const SizedBox(width: 8),
              _filtroChip('RECEBIDAS', 'RECEBIDO'),
              const SizedBox(width: 8),
              _filtroChip('ENVIADAS',  'ENVIADO'),
              const SizedBox(width: 8),
              _filtroChip('MINERADAS', 'MINERADO'),
              const SizedBox(width: 8),
              _filtroChip('PLG-G',     'PLG-G'),
            ],
          ),
        ),
        Expanded(
          child: txs.isEmpty
              ? const Center(child: Text('Nenhuma transação',
                  style: TextStyle(color: PlegmaColors.textDim)))
              : ListView.separated(
                  padding         : const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount       : txs.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder     : (_, i) {
                    final tx  = txs[i];
                    final cor = tx.isEntrada ? PlegmaColors.green : PlegmaColors.red;
                    final icon = {
                      'ENVIADO'         : '↑',
                      'RECEBIDO'        : '↓',
                      'MINERADO'        : '⬡',
                      'VESTING_LIBERADO': '✓',
                      'PLG-G'           : '⬡',
                    }[tx.tipo] ?? '·';
                    return PlegmaCard(
                      child: Row(
                        children: [
                          Container(
                            width     : 36, height: 36,
                            decoration: BoxDecoration(
                              color       : cor.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Center(child: Text(icon,
                                style: TextStyle(fontSize: 16, color: cor))),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(tx.tipo.replaceAll('_', ' '), style: const TextStyle(
                                  fontSize: 11, color: PlegmaColors.textDim, letterSpacing: 1,
                                )),
                                Text(tx.contraparte, style: const TextStyle(
                                  fontSize: 12, color: PlegmaColors.text,
                                ), maxLines: 1, overflow: TextOverflow.ellipsis),
                                if (tx.fonte.isNotEmpty)
                                  Text(tx.fonte, style: const TextStyle(
                                    fontSize: 10, color: PlegmaColors.cyan,
                                  ), maxLines: 1, overflow: TextOverflow.ellipsis),
                                Text(tx.data, style: const TextStyle(
                                  fontSize: 10, color: PlegmaColors.textDim,
                                )),
                              ],
                            ),
                          ),
                          Text(
                            '${tx.isEntrada ? '+' : '-'}${fmtPlg(tx.amount)}',
                            style: TextStyle(fontSize: 12, color: cor,
                                fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _filtroChip(String label, String? filtro) {
    final active = _filtro == filtro;
    return GestureDetector(
      onTap: () {
        setState(() => _filtro = filtro);
        widget.wallet.fetchExtrato(filtro: filtro);
      },
      child: Container(
        padding   : const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color       : active
              ? PlegmaColors.cyan.withValues(alpha: 0.15)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          border      : Border.all(
            color: active ? PlegmaColors.cyan : PlegmaColors.border,
          ),
        ),
        child: Text(label, style: TextStyle(
          fontSize: 10, letterSpacing: 1,
          color: active ? PlegmaColors.cyan : PlegmaColors.textDim,
        )),
      ),
    );
  }
}

// ── Scanner QR — selecionar endereço PLG destino ──────────────────────────────
class _PlgQrScannerPage extends StatefulWidget {
  const _PlgQrScannerPage();

  @override
  State<_PlgQrScannerPage> createState() => _PlgQrScannerPageState();
}

class _PlgQrScannerPageState extends State<_PlgQrScannerPage> {
  bool _lido = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        leading: IconButton(
          icon   : const Icon(Icons.close, color: PlegmaColors.text),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'LER ENDEREÇO PLG',
          style: TextStyle(color: PlegmaColors.cyan, fontSize: 12, letterSpacing: 2),
        ),
      ),
      body: Stack(
        children: [
          MobileScanner(
            onDetect: (capture) {
              if (_lido) return;
              final valor = capture.barcodes.firstOrNull?.rawValue;
              if (valor != null && valor.isNotEmpty) {
                _lido = true;
                Navigator.pop(context, valor);
              }
            },
          ),
          Center(
            child: Container(
              width : 240,
              height: 240,
              decoration: BoxDecoration(
                border      : Border.all(color: PlegmaColors.cyan, width: 2),
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          Positioned(
            bottom: 60, left: 0, right: 0,
            child: Column(
              children: [
                const Text(
                  'Aponte para o QR code do endereço PLG',
                  style: TextStyle(color: PlegmaColors.text, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text(
                    'CANCELAR',
                    style: TextStyle(color: PlegmaColors.red, letterSpacing: 2),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
