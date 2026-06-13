import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/validator_provider.dart';
import '../../providers/wallet_provider.dart';
import '../../widgets/plegma_card.dart';

class ValidatorScreen extends StatelessWidget {
  const ValidatorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final v      = context.watch<ValidatorProvider>();
    final wallet = context.watch<WalletProvider>();

    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        title: const Text('VALIDADOR', style: TextStyle(letterSpacing: 3)),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: StatusBadge(
              label : v.nodeType,
              color : v.nodeType == 'PROVER'
                  ? PlegmaColors.amber
                  : PlegmaColors.cyan,
            ),
          ),
        ],
      ),
      body: ListView(
        padding : const EdgeInsets.all(16),
        children: [

          // ── Botão ligar/desligar ──
          GestureDetector(
            onTap: () => v.toggleMineracao(),
            child: Container(
              height    : 140,
              decoration: BoxDecoration(
                color         : v.minerando
                    ? PlegmaColors.green.withValues(alpha: 0.08)
                    : PlegmaColors.bg2,
                borderRadius  : BorderRadius.circular(20),
                border        : Border.all(
                  color : v.minerando
                      ? PlegmaColors.green.withValues(alpha: 0.5)
                      : PlegmaColors.border,
                  width : 2,
                ),
                boxShadow     : v.minerando
                    ? [BoxShadow(
                        color     : PlegmaColors.green.withValues(alpha: 0.15),
                        blurRadius: 20,
                        spreadRadius: 2,
                      )]
                    : [],
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    v.minerando
                        ? Icons.pause_circle_filled
                        : Icons.play_circle_filled,
                    size  : 52,
                    color : v.minerando
                        ? PlegmaColors.green
                        : PlegmaColors.textDim,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    v.minerando ? 'MINERANDO' : 'PAUSADO',
                    style: TextStyle(
                      fontSize     : 14,
                      fontWeight   : FontWeight.bold,
                      color        : v.minerando
                          ? PlegmaColors.green
                          : PlegmaColors.textDim,
                      letterSpacing: 3,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    v.minerando
                        ? 'Toque para pausar'
                        : 'Toque para iniciar',
                    style: const TextStyle(
                      fontSize: 11, color: PlegmaColors.textDim,
                    ),
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
                      const PlegmaLabel('Hashrate Rede'),
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

          // ── Badge de boost PLG-G — exibido quando boost > 1.0 ──
          if ((wallet.wallet?.boostMineracao ?? 1.0) > 1.0)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: PlegmaColors.amber.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(
                        color: PlegmaColors.amber.withValues(alpha: 0.4),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.bolt,
                            size: 14, color: PlegmaColors.amber),
                        const SizedBox(width: 4),
                        Text(
                          'BOOST PLG-G: ${wallet.wallet!.boostMineracao}x'
                          ' (${wallet.wallet!.categoria})',
                          style: const TextStyle(
                            fontSize: 11,
                            color: PlegmaColors.amber,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1,
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
                _infoRow('Nós Ativos',  v.nosAtivos.toString()),
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
                  'disponíveis, com teto de 10% por nó.',
                  style: TextStyle(
                    fontSize: 12, color: PlegmaColors.textDim,
                    height  : 1.6,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value) => Row(
    children: [
      Text(label, style: const TextStyle(
        fontSize: 11, color: PlegmaColors.textDim, letterSpacing: 1,
      )),
      const Spacer(),
      Text(value, style: const TextStyle(
        fontSize: 11, color: PlegmaColors.text,
      )),
    ],
  );
}
