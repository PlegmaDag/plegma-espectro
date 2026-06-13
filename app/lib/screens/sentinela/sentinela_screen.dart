import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/validator_provider.dart';
import '../../providers/wallet_provider.dart';
import '../../widgets/plegma_card.dart';


class SentinelaScreen extends StatefulWidget {
  const SentinelaScreen({super.key});
  @override
  State<SentinelaScreen> createState() => _SentinelaScreenState();
}

class _SentinelaScreenState extends State<SentinelaScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  final _proversKey = GlobalKey<_ProversTabState>();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _tabs.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final v = context.watch<ValidatorProvider>();

    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        title: const Text('SENTINELA', style: TextStyle(letterSpacing: 3)),
        actions: [
          if (_tabs.index == 0)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: StatusBadge(
                label: v.nodeType,
                color: v.nodeType == 'PROVER' ? PlegmaColors.amber : PlegmaColors.cyan,
              ),
            ),
          if (_tabs.index == 1)
            IconButton(
              onPressed: () => _proversKey.currentState?.startScan(),
              icon: const Icon(Icons.qr_code_scanner),
              tooltip: 'Vincular novo Prover',
            ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: PlegmaColors.cyan,
          unselectedLabelColor: PlegmaColors.textDim,
          indicatorColor: PlegmaColors.cyan,
          indicatorSize: TabBarIndicatorSize.label,
          labelStyle: const TextStyle(fontSize: 10, letterSpacing: 2),
          tabs: const [Tab(text: 'VALIDADOR'), Tab(text: 'PROVERS')],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          const _ValidadorTab(),
          _ProversTab(key: _proversKey),
        ],
      ),
      floatingActionButton: _tabs.index == 1
          ? FloatingActionButton(
              onPressed: () => _proversKey.currentState?.startScan(),
              backgroundColor: PlegmaColors.cyan,
              foregroundColor: Colors.black,
              tooltip: 'Vincular Prover',
              child: const Icon(Icons.add),
            )
          : null,
    );
  }
}

// ── Tab Validador ─────────────────────────────────────────────────────────────
class _ValidadorTab extends StatefulWidget {
  const _ValidadorTab();
  @override
  State<_ValidadorTab> createState() => _ValidadorTabState();
}

class _ValidadorTabState extends State<_ValidadorTab>
    with SingleTickerProviderStateMixin {
  late AnimationController _celebCtrl;
  late Animation<double>    _celebScale;
  late Animation<double>    _celebOpacity;

  @override
  void initState() {
    super.initState();
    _celebCtrl = AnimationController(
      vsync   : this,
      duration: const Duration(milliseconds: 600),
    );
    _celebScale   = CurvedAnimation(parent: _celebCtrl, curve: Curves.elasticOut);
    _celebOpacity = CurvedAnimation(parent: _celebCtrl, curve: Curves.easeIn);
  }

  @override
  void dispose() {
    _celebCtrl.dispose();
    super.dispose();
  }

  Future<void> _onToggle(ValidatorProvider v) async {
    if (v.minerando) {
      // Confirmação de desativação
      final confirm = await showDialog<bool>(
        context: context,
        builder: (_) => Dialog(
          backgroundColor: PlegmaColors.bg2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(color: PlegmaColors.red.withValues(alpha: 0.4)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.warning_amber_rounded, size: 40, color: PlegmaColors.amber),
                const SizedBox(height: 12),
                const Text(
                  'Tem certeza que realmente\nprecisa desativar?',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 14, color: PlegmaColors.text,
                      fontWeight: FontWeight.bold, height: 1.4),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Você vai perder o uptime e as recompensas\npendentes deste ciclo.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11, color: PlegmaColors.textDim, height: 1.5),
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.pop(context, false),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: PlegmaColors.border),
                        ),
                        child: const Text('MANTER',
                            style: TextStyle(color: PlegmaColors.textDim, fontSize: 11)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => Navigator.pop(context, true),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: PlegmaColors.red.withValues(alpha: 0.15),
                          foregroundColor: PlegmaColors.red,
                          side: BorderSide(color: PlegmaColors.red.withValues(alpha: 0.5)),
                        ),
                        child: const Text('DESATIVAR',
                            style: TextStyle(fontSize: 11, letterSpacing: 1)),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      if (confirm == true) v.toggleMineracao();
    } else {
      // Ativar → aguarda confirmação da API antes de celebrar
      final ok = await v.toggleMineracao();
      if (!mounted) return;
      if (ok) {
        _celebCtrl.forward(from: 0.0);
        await Future.delayed(const Duration(milliseconds: 2600));
        if (mounted) _celebCtrl.reverse();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Carteira não detectada. Aguarde o carregamento ou reinstale o app.'),
            backgroundColor: Color(0xFFFF4757),
            duration: Duration(seconds: 4),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final v      = context.watch<ValidatorProvider>();
    final wallet = context.watch<WalletProvider>();

    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.all(16),
          children: [

        // ── Botão ligar/desligar ──
        GestureDetector(
          onTap: () => _onToggle(v),
          child: Container(
            height: 140,
            decoration: BoxDecoration(
              color: v.minerando
                  ? PlegmaColors.green.withValues(alpha: 0.08)
                  : PlegmaColors.bg2,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: v.minerando
                    ? PlegmaColors.green.withValues(alpha: 0.5)
                    : PlegmaColors.border,
                width: 2,
              ),
              boxShadow: v.minerando
                  ? [BoxShadow(
                      color: PlegmaColors.green.withValues(alpha: 0.15),
                      blurRadius: 20,
                      spreadRadius: 2,
                    )]
                  : [],
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  v.minerando ? Icons.pause_circle_filled : Icons.play_circle_filled,
                  size: 52,
                  color: v.minerando ? PlegmaColors.green : PlegmaColors.textDim,
                ),
                const SizedBox(height: 8),
                Text(
                  v.minerando ? 'MINERANDO' : 'PAUSADO',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: v.minerando ? PlegmaColors.green : PlegmaColors.textDim,
                    letterSpacing: 3,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  v.minerando ? 'Toque para pausar' : 'Toque para iniciar',
                  style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim),
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 16),

        // ── Métricas ──
        Row(
          children: [
            Expanded(
              child: PlegmaCard(
                topAccent: PlegmaColors.cyan,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Hashrate'),
                    const SizedBox(height: 6),
                    Text(
                      '${v.hashrate.toStringAsFixed(2)} H/s',
                      style: const TextStyle(
                        fontSize: 16, color: PlegmaColors.cyan,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: PlegmaCard(
                topAccent: PlegmaColors.green,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Recompensa'),
                    const SizedBox(height: 6),
                    Text(
                      fmtPlg(v.recompensa),
                      style: const TextStyle(
                        fontSize: 13, color: PlegmaColors.green,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 10),

        Row(
          children: [
            Expanded(
              child: PlegmaCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Vértices Aceitos'),
                    const SizedBox(height: 6),
                    Text(
                      v.aceitas.toString(),
                      style: const TextStyle(
                        fontSize: 16, color: PlegmaColors.text,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: PlegmaCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Uptime'),
                    const SizedBox(height: 6),
                    Text(
                      v.uptime,
                      style: const TextStyle(
                        fontSize: 15, color: PlegmaColors.amber,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 10),

        // ── Badge de boost PLG-G ──
        if ((wallet.wallet?.boostMineracao ?? 1.0) > 1.0)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: PlegmaColors.amber.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: PlegmaColors.amber.withValues(alpha: 0.4)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.bolt, size: 14, color: PlegmaColors.amber),
                      const SizedBox(width: 4),
                      Text(
                        'BOOST PLG-G: ${wallet.wallet!.boostMineracao}x'
                        ' (${wallet.wallet!.categoria})',
                        style: const TextStyle(
                          fontSize: 11, color: PlegmaColors.amber,
                          fontWeight: FontWeight.bold, letterSpacing: 1,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

        const SizedBox(height: 6),

        // ── Status da DAG ──
        PlegmaCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const PlegmaLabel('Status da DAG'),
                  StatusBadge(
                    label: v.dagOnline ? 'ONLINE' : 'OFFLINE',
                    color: v.dagOnline ? PlegmaColors.green : PlegmaColors.red,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _infoRow('Nós Ativos', v.nosAtivos.toString()),
              const SizedBox(height: 8),
              _infoRow('Último Hash', v.lastHash),
              const SizedBox(height: 8),
              _infoRow('Pool',
                  v.nodeType == 'PROVER' ? 'Prover (40%)' : 'Validator (60%)'),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // ── Estatuto §14 ──
        PlegmaCard(
          borderColor: PlegmaColors.purple.withValues(alpha: 0.3),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              PlegmaLabel('Cláusula 14ª — Justiça Computacional',
                  color: PlegmaColors.purple),
              SizedBox(height: 8),
              Text(
                'A potência de hardware não confere prioridade de validação. '
                'O trabalho é distribuído equitativamente entre os Provers '
                'disponíveis.',
                style: TextStyle(
                  fontSize: 12, color: PlegmaColors.textDim, height: 1.6,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 24),
          ],
        ),

        // ── Overlay de celebração ao ativar ──
        AnimatedBuilder(
          animation: _celebCtrl,
          builder: (_, __) {
            if (_celebCtrl.value == 0.0) return const SizedBox.shrink();
            return Positioned.fill(
              child: IgnorePointer(
                child: Container(
                  color: Colors.black.withValues(alpha: 0.55 * _celebOpacity.value),
                  child: Center(
                    child: ScaleTransition(
                      scale: _celebScale,
                      child: FadeTransition(
                        opacity: _celebOpacity,
                        child: Container(
                          margin: const EdgeInsets.symmetric(horizontal: 32),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 28, vertical: 32),
                          decoration: BoxDecoration(
                            color: PlegmaColors.bg2,
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                                color: PlegmaColors.green.withValues(alpha: 0.5),
                                width: 1.5),
                            boxShadow: [
                              BoxShadow(
                                color: PlegmaColors.green.withValues(alpha: 0.2),
                                blurRadius: 30,
                                spreadRadius: 4,
                              ),
                            ],
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 72, height: 72,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: PlegmaColors.green.withValues(alpha: 0.12),
                                  border: Border.all(
                                      color: PlegmaColors.green.withValues(alpha: 0.5)),
                                ),
                                child: const Icon(Icons.check_circle_outline,
                                    size: 38, color: PlegmaColors.green),
                              ),
                              const SizedBox(height: 16),
                              const Text('Parabéns!',
                                style: TextStyle(
                                  fontSize: 20, color: PlegmaColors.green,
                                  fontWeight: FontWeight.bold, letterSpacing: 1,
                                ),
                              ),
                              const SizedBox(height: 8),
                              const Text(
                                'Você está ajudando a\nconstruir o futuro.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 14, color: PlegmaColors.text,
                                  height: 1.5,
                                ),
                              ),
                              const SizedBox(height: 4),
                              const Text(
                                'A rede PLEGMA agradece.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 11, color: PlegmaColors.textDim,
                                  letterSpacing: 1,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _infoRow(String label, String value) => Row(
    children: [
      Text(label, style: const TextStyle(
        fontSize: 11, color: PlegmaColors.textDim, letterSpacing: 1,
      )),
      const Spacer(),
      Text(value, style: const TextStyle(fontSize: 11, color: PlegmaColors.text)),
    ],
  );
}

// ── Tab Provers ───────────────────────────────────────────────────────────────
class _ProversTab extends StatefulWidget {
  const _ProversTab({super.key});
  @override
  State<_ProversTab> createState() => _ProversTabState();
}

class _ProversTabState extends State<_ProversTab> {
  bool _scanQR = false;

  final Map<String, Color> _corCategoria = {
    'GPU'         : PlegmaColors.cyan,
    'ASIC'        : PlegmaColors.amber,
    'SERVER'      : PlegmaColors.purple,
    'DESKTOP_HIGH': PlegmaColors.green,
    'NOTEBOOK'    : PlegmaColors.textDim,
  };

  final Map<String, String> _iconeCategoria = {
    'GPU'         : '🖥',
    'ASIC'        : '⚙',
    'SERVER'      : '🖧',
    'DESKTOP_HIGH': '💻',
    'NOTEBOOK'    : '💻',
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<WalletProvider>().fetchProvers();
    });
  }

  void startScan() => setState(() => _scanQR = true);

  Future<void> _processarQRVinculo(String raw) async {
    setState(() => _scanQR = false);

    String? nodeId, categoria;
    int score = 0;
    try {
      final uri = Uri.parse(raw.replaceFirst('plegma://', 'https://plegma.local/'));
      nodeId    = uri.queryParameters['node_id'];
      categoria = uri.queryParameters['categoria'];
      score     = int.tryParse(uri.queryParameters['score'] ?? '0') ?? 0;
    } catch (e) { debugPrint('Erro: $e'); }

    if (nodeId == null || nodeId.isEmpty) {
      _showSnack('QR inválido — não é um QR de vínculo PLEGMA', PlegmaColors.red);
      return;
    }

    final result = await context.read<WalletProvider>().vincularProver(
      nodeId   : nodeId,
      categoria: categoria ?? 'DESKTOP',
      score    : score,
    );

    if (result == true) {
      _showSnack('✓ Prover $nodeId vinculado com sucesso!', PlegmaColors.green);
      if (mounted) context.read<WalletProvider>().fetchProvers();
    } else {
      _showSnack('✗ Falha ao vincular — tente novamente', PlegmaColors.red);
    }
  }

  void _showSnack(String msg, Color cor) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: cor));
  }

  @override
  Widget build(BuildContext context) {
    final wallet  = context.watch<WalletProvider>();
    final provers = wallet.provers;

    return Stack(
      children: [

        RefreshIndicator(
          onRefresh: wallet.fetchProvers,
          color    : PlegmaColors.cyan,
          child    : ListView(
            padding : const EdgeInsets.all(16),
            children: [

              // ── Cards de resumo (3 cards — igual ao web dashboard) ──
              // Card 1 + Card 2: mesma altura na mesma linha
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Card 1: Dispositivos Vinculados (Provers + Val)
                    Expanded(
                      child: PlegmaCard(
                        topAccent: PlegmaColors.cyan,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const PlegmaLabel('Dispositivos Vinculados'),
                            const SizedBox(height: 12),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('PROVERS',
                                    style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 2)),
                                Text(
                                  wallet.countProvers.toString(),
                                  style: const TextStyle(fontSize: 16, color: PlegmaColors.cyan, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                                ),
                              ],
                            ),
                            const Divider(color: PlegmaColors.border, height: 14, thickness: 1),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('VAL',
                                    style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 2)),
                                Text(
                                  wallet.countValidadores.toString(),
                                  style: const TextStyle(fontSize: 16, color: PlegmaColors.purple, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // Card 2: Ganhos Totais
                    Expanded(
                      child: PlegmaCard(
                        topAccent: PlegmaColors.amber,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const PlegmaLabel('Ganhos Totais'),
                            const SizedBox(height: 6),
                            Text(
                              fmtPlg(provers.fold(0.0, (s, p) => s + p.ganhos)),
                              style: const TextStyle(fontSize: 16, color: PlegmaColors.amber, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                            ),
                            const SizedBox(height: 2),
                            const Text('Todos os dispositivos ativos',
                                style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              // Card 3: Justiça Computacional — full-width retangular
              PlegmaCard(
                child: Row(
                  children: [
                    Container(
                      width: 36, height: 36,
                      decoration: BoxDecoration(
                        color: PlegmaColors.green.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: PlegmaColors.green.withValues(alpha: 0.25)),
                      ),
                      child: const Center(
                        child: Text('⚖', style: TextStyle(fontSize: 18)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          PlegmaLabel('Justiça Computacional'),
                          SizedBox(height: 4),
                          Text(
                            'Trabalho distribuído de forma equitativa. '
                            'Potência de hardware não confere prioridade sobre tarefas.',
                            style: TextStyle(fontSize: 10, color: PlegmaColors.textDim, height: 1.6),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 12),

              // ── Como vincular ──
              PlegmaCard(
                borderColor: PlegmaColors.cyanBord,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PlegmaLabel('Como Vincular um Prover',
                        color: PlegmaColors.cyan),
                    const SizedBox(height: 12),
                    _passoRow('1', 'Baixe o minerador PLEGMA no PC que deseja vincular'),
                    _passoRow('2', 'O minerador detecta o hardware e classifica como Validator ou Prover'),
                    _passoRow('3', 'Escaneie o QR de vínculo exibido no minerador com o app PLEGMA'),
                    _passoRow('4', 'Recompensas vão direto para o endereço PLG do celular dono'),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // ── Lista de Provers ──
              if (provers.isEmpty)
                PlegmaCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const PlegmaLabel('Provers Vinculados'),
                      const SizedBox(height: 10),
                      // Cabeçalho da tabela
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        decoration: BoxDecoration(
                          color: PlegmaColors.bg2.withValues(alpha: 0.8),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Row(
                          children: [
                            SizedBox(width: 28),
                            Expanded(flex: 3, child: Text('NODE ID',
                                style: TextStyle(fontSize: 8, color: PlegmaColors.textDim, letterSpacing: 1.5))),
                            Expanded(flex: 2, child: Text('CATEGORIA',
                                style: TextStyle(fontSize: 8, color: PlegmaColors.textDim, letterSpacing: 1.5))),
                            Expanded(flex: 1, child: Text('SCORE',
                                style: TextStyle(fontSize: 8, color: PlegmaColors.textDim, letterSpacing: 1.5),
                                textAlign: TextAlign.center)),
                            Expanded(flex: 2, child: Text('GANHOS',
                                style: TextStyle(fontSize: 8, color: PlegmaColors.textDim, letterSpacing: 1.5),
                                textAlign: TextAlign.right)),
                            SizedBox(width: 52),
                          ],
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Divider(color: PlegmaColors.border, height: 1),
                      const SizedBox(height: 24),
                      const Center(
                        child: Column(
                          children: [
                            Text('⛓', style: TextStyle(fontSize: 28)),
                            SizedBox(height: 8),
                            Text('Nenhum Prover vinculado',
                              style: TextStyle(fontSize: 12, color: PlegmaColors.text, fontWeight: FontWeight.bold)),
                            SizedBox(height: 4),
                            Text('Escaneie o QR do minerador para adicionar.',
                              style: TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                )
              else
                ...provers.map((p) {
                  final cor   = _corCategoria[p.categoria] ?? PlegmaColors.textDim;
                  final icone = _iconeCategoria[p.categoria] ?? '⚙';
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: PlegmaCard(
                      borderColor: p.ativo
                          ? PlegmaColors.green.withValues(alpha: 0.3)
                          : PlegmaColors.border,
                      child: Row(
                        children: [
                          Container(
                            width: 44, height: 44,
                            decoration: BoxDecoration(
                              color       : cor.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(10),
                              border      : Border.all(color: cor.withValues(alpha: 0.3)),
                            ),
                            child: Center(
                              child: Text(icone, style: const TextStyle(fontSize: 20)),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(p.nodeId,
                                  style: const TextStyle(
                                    fontSize: 12, color: PlegmaColors.text,
                                    fontWeight: FontWeight.bold,
                                  ),
                                  maxLines: 1, overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 2),
                                Row(
                                  children: [
                                    Text(p.categoria,
                                      style: TextStyle(
                                          fontSize: 10, color: cor, letterSpacing: 1)),
                                    const Text(' · ',
                                        style: TextStyle(color: PlegmaColors.textDim)),
                                    Text('Score: ${p.score}',
                                      style: const TextStyle(
                                          fontSize: 10, color: PlegmaColors.textDim)),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                Text('+${fmtPlg(p.ganhos)} · Pool 40%',
                                  style: const TextStyle(
                                      fontSize: 10, color: PlegmaColors.amber)),
                                if (p.ultimoPing.isNotEmpty) ...[
                                  const SizedBox(height: 2),
                                  Text('Ping: ${p.ultimoPing}',
                                    style: const TextStyle(
                                        fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 0.5)),
                                ],
                              ],
                            ),
                          ),
                          Column(
                            children: [
                              StatusBadge(
                                label: p.ativo ? 'ATIVO' : 'OFF',
                                color: p.ativo
                                    ? PlegmaColors.green
                                    : PlegmaColors.textDim,
                              ),
                              const SizedBox(height: 6),
                              GestureDetector(
                                onTap: () => _confirmarDesvinculo(p.nodeId),
                                child: const Text('REMOVER',
                                  style: TextStyle(
                                      fontSize: 9, color: PlegmaColors.red,
                                      letterSpacing: 1)),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                }),

              const SizedBox(height: 8),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  'Trabalho equitativo · cada dispositivo contribui de forma igual',
                  style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1),
                  textAlign: TextAlign.center,
                ),
              ),

              const SizedBox(height: 24),
            ],
          ),
        ),

        // ── Scanner QR ──
        if (_scanQR)
          Positioned.fill(
            child: Container(
              color: Colors.black,
              child: Stack(
                children: [
                  MobileScanner(
                    onDetect: (capture) {
                      final barcode = capture.barcodes.firstOrNull;
                      if (barcode?.rawValue != null) {
                        _processarQRVinculo(barcode!.rawValue!);
                      }
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
                    child: Column(
                      children: [
                        const Text(
                          'Aponte para o QR de vínculo do minerador',
                          style: TextStyle(color: PlegmaColors.text, fontSize: 13),
                        ),
                        const SizedBox(height: 20),
                        TextButton(
                          onPressed: () => setState(() => _scanQR = false),
                          child: const Text('CANCELAR',
                            style: TextStyle(color: PlegmaColors.red, letterSpacing: 2)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _passoRow(String num, String texto) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22, height: 22,
          decoration: BoxDecoration(
            color       : PlegmaColors.cyanDim,
            borderRadius: BorderRadius.circular(11),
            border      : Border.all(color: PlegmaColors.cyanBord),
          ),
          child: Center(
            child: Text(num, style: const TextStyle(
              fontSize: 10, color: PlegmaColors.cyan, fontWeight: FontWeight.bold,
            )),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(texto, style: const TextStyle(
            fontSize: 12, color: PlegmaColors.textDim, height: 1.6,
          )),
        ),
      ],
    ),
  );

  void _confirmarDesvinculo(String nodeId) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: PlegmaColors.bg2,
        title: const Text('Desvincular Prover',
            style: TextStyle(color: PlegmaColors.cyan, fontSize: 14)),
        content: Text(
          'Remover "$nodeId" da rede?\n\nEle perderá acesso até ser vinculado novamente.',
          style: const TextStyle(color: PlegmaColors.textDim, fontSize: 13),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCELAR',
                style: TextStyle(color: PlegmaColors.textDim)),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _showSnack('Prover desvinculado', PlegmaColors.amber);
            },
            child: const Text('REMOVER',
                style: TextStyle(color: PlegmaColors.red)),
          ),
        ],
      ),
    );
  }
}
