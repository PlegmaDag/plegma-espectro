import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/wallet_provider.dart';
import '../../providers/validator_provider.dart';
import '../../widgets/plegma_card.dart';

class HomeDashboard extends StatelessWidget {
  const HomeDashboard({super.key});

  Widget _buildFaseBanner(bool transacoesAtivas) {
    final label = transacoesAtivas ? 'GENESIS ATIVO · AO VIVO' : 'FASE ZERO · READ_ONLY';
    final color = transacoesAtivas ? PlegmaColors.green : PlegmaColors.amber;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color       : color.withOpacity(0.07),
        borderRadius: BorderRadius.circular(6),
        border      : Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width : 6,
            height: 6,
            decoration: BoxDecoration(
              color    : color,
              shape    : BoxShape.circle,
              boxShadow: [BoxShadow(color: color.withOpacity(0.5), blurRadius: 4)],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              fontSize    : 10,
              color       : color,
              letterSpacing: 1.5,
              fontWeight  : FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNetStat(String label, int value, Color color) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: PlegmaColors.textDim),
        ),
        Text(
          value.toString(),
          style: TextStyle(
            fontSize: 12,
            color: color,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Color _categoriaColor(String cat) {
    switch (cat) {
      case 'MASTER':    return const Color(0xFF00F2FF);
      case 'SENTINELA': return const Color(0xFFa78bfa);
      default:          return const Color(0xFF64748b);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wallet    = context.watch<WalletProvider>();
    final validator = context.watch<ValidatorProvider>();

    return Scaffold(
      backgroundColor : PlegmaColors.bg,
      appBar          : AppBar(
        title   : Row(
          mainAxisSize: MainAxisSize.min,
          children    : [
            Image.asset(
              'assets/images/logo.png',
              width : 28,
              height: 28,
            ),
            const SizedBox(width: 10),
            const Text(
              'PLEGMA DAG',
              style: TextStyle(fontSize: 14, letterSpacing: 3),
            ),
          ],
        ),
        actions : [
          Padding(
            padding : const EdgeInsets.only(right: 16),
            child   : StatusBadge(
              label  : validator.dagOnline ? 'ONLINE' : 'OFFLINE',
              color  : validator.dagOnline ? PlegmaColors.green : PlegmaColors.red,
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh   : () async {
          await wallet.fetchStatus();
          await validator.inicializar();
        },
        color       : PlegmaColors.cyan,
        child: ListView(
          padding  : const EdgeInsets.all(16),
          children : [

            // ── Fase da rede ──
            _buildFaseBanner(wallet.transacoesAtivas),
            const SizedBox(height: 12),

            // ── Saldo rápido ──
            PlegmaCard(
              topAccent: PlegmaColors.cyan,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const PlegmaLabel('Saldo Disponível'),
                  const SizedBox(height: 8),
                  PlegmaValue(
                    wallet.wallet != null
                        ? fmtPlg(wallet.wallet!.disponivel)
                        : '-- \$PLG',
                    color   : PlegmaColors.cyan,
                    fontSize: 22,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    wallet.wallet != null
                        ? '≈ ${fmtUsdt(wallet.wallet!.disponivelUsdt)}'
                        : '≈ --',
                    style: const TextStyle(
                      fontSize  : 12,
                      color     : PlegmaColors.textDim,
                      letterSpacing: 1,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 12),

            // ── Card Sócio Genesis — exibido apenas se usuário tem PLG-G ──
            if ((wallet.wallet?.plggTotal ?? 0) > 0) ...[
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: const Color(0xFF0a1628),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: _categoriaColor(
                            wallet.wallet?.categoria ?? 'APOIADOR')
                        .withValues(alpha: 0.35),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF00F2FF).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(
                          color:
                              const Color(0xFF00F2FF).withValues(alpha: 0.4),
                        ),
                      ),
                      child: const Text(
                        'SÓCIO GENESIS',
                        style: TextStyle(
                          fontSize: 9,
                          color: Color(0xFF00F2FF),
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '${wallet.wallet?.categoria ?? 'APOIADOR'}'
                        ' · boost ${wallet.wallet?.boostMineracao.toStringAsFixed(1) ?? '1.0'}x de mineração',
                        style: TextStyle(
                          fontSize: 12,
                          color: _categoriaColor(
                              wallet.wallet?.categoria ?? 'APOIADOR'),
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
            ],

            // ── Cards de métricas 2x2 ──
            Row(
              children: [
                Expanded(
                  child: PlegmaCard(
                    topAccent: PlegmaColors.amber,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const PlegmaLabel('Em Vesting'),
                        const SizedBox(height: 8),
                        Text(
                          wallet.wallet != null
                              ? fmtPlg(wallet.wallet!.vestingLocked)
                              : '-- \$PLG',
                          style: const TextStyle(
                            fontSize: 13, color: PlegmaColors.amber,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        if (wallet.wallet?.proximaLiberacao != null)
                          Text(
                            'Libera em ${wallet.wallet!.proximaLiberacao}d',
                            style: const TextStyle(
                              fontSize: 10, color: PlegmaColors.textDim,
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
                        const PlegmaLabel('Hashrate'),
                        const SizedBox(height: 8),
                        Text(
                          '${validator.hashrate.toStringAsFixed(2)} H/s',
                          style: const TextStyle(
                            fontSize: 13, color: PlegmaColors.green,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          validator.nodeType,
                          style: const TextStyle(
                            fontSize: 10, color: PlegmaColors.textDim,
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
                        const PlegmaLabel('Status da Rede'),
                        const SizedBox(height: 10),
                        _buildNetStat('Âncoras',    validator.nosAncoras,        PlegmaColors.cyan),
                        const SizedBox(height: 4),
                        _buildNetStat('Mineradores', validator.nosMineradores,   PlegmaColors.green),
                        const SizedBox(height: 4),
                        _buildNetStat('Validadores', validator.validadoresAtivos, PlegmaColors.amber),
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
                        const PlegmaLabel('Dispositivos'),
                        const SizedBox(height: 10),
                        _buildNetStat('Provers', wallet.countProvers,    PlegmaColors.text),
                        const SizedBox(height: 4),
                        _buildNetStat('Val',     wallet.countValidadores, PlegmaColors.purple),
                      ],
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 16),

            // ── Último vértice ──
            PlegmaCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const PlegmaLabel('Último Vértice DAG'),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      const Icon(
                        Icons.hexagon_outlined,
                        color: PlegmaColors.cyan, size: 14,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          validator.lastHash,
                          style: const TextStyle(
                            fontSize: 11, color: PlegmaColors.cyan,
                            letterSpacing: 1,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Uptime: ${validator.uptime}',
                    style: const TextStyle(
                      fontSize: 10, color: PlegmaColors.textDim, letterSpacing: 1,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // ── Pools 60/40 ──
            PlegmaCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const PlegmaLabel('Divisão de Incentivos — Estatuto §13'),
                  const SizedBox(height: 14),

                  // Validator 60%
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'VALIDATOR POOL',
                          style: TextStyle(
                            fontSize: 10, color: PlegmaColors.cyan,
                            letterSpacing: 1,
                          ),
                        ),
                      ),
                      const Text(
                        '60%',
                        style: TextStyle(
                          fontSize: 11, color: PlegmaColors.cyan,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: LinearProgressIndicator(
                      value           : 0.60,
                      backgroundColor : PlegmaColors.bg3,
                      color           : PlegmaColors.cyan,
                      minHeight       : 4,
                    ),
                  ),

                  const SizedBox(height: 14),

                  // Prover 40%
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'PROVER POOL',
                          style: TextStyle(
                            fontSize: 10, color: PlegmaColors.amber,
                            letterSpacing: 1,
                          ),
                        ),
                      ),
                      const Text(
                        '40%',
                        style: TextStyle(
                          fontSize: 11, color: PlegmaColors.amber,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: LinearProgressIndicator(
                      value           : 0.40,
                      backgroundColor : PlegmaColors.bg3,
                      color           : PlegmaColors.amber,
                      minHeight       : 4,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
