import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/wallet_provider.dart';
import '../../widgets/plegma_card.dart';

class ProversScreen extends StatefulWidget {
  const ProversScreen({super.key});

  @override
  State<ProversScreen> createState() => _ProversScreenState();
}

class _ProversScreenState extends State<ProversScreen> {
  bool _scanQR = false;

  final Map<String, Color> _corCategoria = {
    'GPU'          : PlegmaColors.cyan,
    'ASIC'         : PlegmaColors.amber,
    'SERVER'       : PlegmaColors.purple,
    'DESKTOP_HIGH' : PlegmaColors.green,
    'NOTEBOOK'     : PlegmaColors.textDim,
  };

  final Map<String, String> _iconeCategoria = {
    'GPU'          : '🖥',
    'ASIC'         : '⚙',
    'SERVER'       : '🖧',
    'DESKTOP_HIGH' : '💻',
    'NOTEBOOK'     : '💻',
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<WalletProvider>().fetchProvers();
    });
  }

  Future<void> _processarQRVinculo(String raw) async {
    setState(() => _scanQR = false);

    // QR de vínculo: plegma://prover?node_id=X&categoria=GPU&score=2660
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
      nodeId    : nodeId,
      categoria : categoria ?? 'DESKTOP',
      score     : score,
    );

    if (result == true) {
      _showSnack('✓ Prover $nodeId vinculado com sucesso!', PlegmaColors.green);
      if (mounted) context.read<WalletProvider>().fetchProvers();
    } else {
      _showSnack('✗ Falha ao vincular — tente novamente', PlegmaColors.red);
    }
  }

  void _showSnack(String msg, Color cor) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content         : Text(msg),
      backgroundColor : cor,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final wallet  = context.watch<WalletProvider>();
    final provers = wallet.provers;

    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        title: const Text('PROVERS', style: TextStyle(letterSpacing: 3)),
        actions: [
          IconButton(
            onPressed : () => setState(() => _scanQR = true),
            icon      : const Icon(Icons.qr_code_scanner),
            tooltip   : 'Vincular novo Prover',
          ),
        ],
      ),
      body: Stack(
        children: [

          RefreshIndicator(
            onRefresh   : wallet.fetchProvers,
            color       : PlegmaColors.cyan,
            child       : ListView(
              padding   : const EdgeInsets.all(16),
              children  : [

                // ── Cards de resumo ──
                Row(
                  children: [
                    Expanded(
                      child: PlegmaCard(
                        topAccent: PlegmaColors.amber,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const PlegmaLabel('Provers Ativos'),
                            const SizedBox(height: 6),
                            Text(
                              provers.where((p) => p.ativo).length.toString(),
                              style: const TextStyle(
                                fontSize: 22, color: PlegmaColors.amber,
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
                            const PlegmaLabel('Ganhos Totais'),
                            const SizedBox(height: 6),
                            Text(
                              fmtPlg(provers.fold(
                                  0.0, (s, p) => s + p.ganhos)),
                              style: const TextStyle(
                                fontSize: 12, color: PlegmaColors.green,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
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
                      _passoRow('1', 'Baixe e execute o PLEGMA_Minerador.exe no PC'),
                      _passoRow('2', 'O minerador detecta o hardware e gera um QR de vínculo'),
                      _passoRow('3', 'Toque em ⊕ e escaneie o QR com este app'),
                      _passoRow('4', 'As recompensas vão direto para este endereço PLG'),
                    ],
                  ),
                ),

                const SizedBox(height: 16),

                // ── Lista de Provers ──
                if (provers.isEmpty)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: Text(
                        'Nenhum Prover vinculado.\nEscaneie o QR do minerador para adicionar.',
                        textAlign : TextAlign.center,
                        style     : TextStyle(
                          color: PlegmaColors.textDim, fontSize: 13,
                          height: 1.8,
                        ),
                      ),
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
                            // Ícone categoria
                            Container(
                              width : 44, height: 44,
                              decoration: BoxDecoration(
                                color       : cor.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(10),
                                border      : Border.all(
                                    color: cor.withValues(alpha: 0.3)),
                              ),
                              child: Center(
                                child: Text(icone,
                                    style: const TextStyle(fontSize: 20)),
                              ),
                            ),
                            const SizedBox(width: 12),

                            // Info
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(p.nodeId,
                                    style: const TextStyle(
                                      fontSize: 12, color: PlegmaColors.text,
                                      fontWeight: FontWeight.bold,
                                    ),
                                    maxLines : 1,
                                    overflow : TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 2),
                                  Row(
                                    children: [
                                      Text(
                                        p.categoria,
                                        style: TextStyle(
                                          fontSize: 10, color: cor,
                                          letterSpacing: 1,
                                        ),
                                      ),
                                      const Text(' · ',
                                          style: TextStyle(
                                              color: PlegmaColors.textDim)),
                                      Text(
                                        'Score: ${p.score}',
                                        style: const TextStyle(
                                          fontSize: 10,
                                          color: PlegmaColors.textDim,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    '+${fmtPlg(p.ganhos)} · Pool 40%',
                                    style: const TextStyle(
                                      fontSize: 10, color: PlegmaColors.amber,
                                    ),
                                  ),
                                ],
                              ),
                            ),

                            // Status
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
                                  child: const Text(
                                    'REMOVER',
                                    style: TextStyle(
                                      fontSize: 9, color: PlegmaColors.red,
                                      letterSpacing: 1,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  }),

                // ── Estatuto §14 ──
                const SizedBox(height: 8),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 4),
                  child: Text(
                    'Cláusula 14ª: Teto de 10% do trabalho por Prover — Estatuto §13',
                    style: TextStyle(
                      fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1,
                    ),
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
                        width : 240, height: 240,
                        decoration: BoxDecoration(
                          border      : Border.all(
                              color: PlegmaColors.cyan, width: 2),
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
                            style: TextStyle(
                              color: PlegmaColors.text, fontSize: 13,
                            ),
                          ),
                          const SizedBox(height: 20),
                          TextButton(
                            onPressed: () => setState(() => _scanQR = false),
                            child: const Text('CANCELAR',
                              style: TextStyle(
                                color: PlegmaColors.red, letterSpacing: 2,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
      floatingActionButton: _scanQR
          ? null
          : FloatingActionButton(
              onPressed     : () => setState(() => _scanQR = true),
              backgroundColor: PlegmaColors.cyan,
              foregroundColor: Colors.black,
              child         : const Icon(Icons.add),
              tooltip       : 'Vincular Prover',
            ),
    );
  }

  Widget _passoRow(String num, String texto) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width : 22, height: 22,
          decoration: BoxDecoration(
            color       : PlegmaColors.cyanDim,
            borderRadius: BorderRadius.circular(11),
            border      : Border.all(color: PlegmaColors.cyanBord),
          ),
          child: Center(
            child: Text(num, style: const TextStyle(
              fontSize: 10, color: PlegmaColors.cyan,
              fontWeight: FontWeight.bold,
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
            onPressed: () async {
              Navigator.pop(context);
              final ok = await context.read<WalletProvider>().desvincularProver(nodeId);
              if (mounted) {
                _showSnack(
                  ok ? '✓ Prover $nodeId removido.' : '✗ Falha ao remover — tente novamente.',
                  ok ? PlegmaColors.amber : PlegmaColors.red,
                );
              }
            },
            child: const Text('REMOVER',
                style: TextStyle(color: PlegmaColors.red)),
          ),
        ],
      ),
    );
  }
}
