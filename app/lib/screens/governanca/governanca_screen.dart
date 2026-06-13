import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/validator_provider.dart';
import '../../providers/wallet_provider.dart';
import '../../widgets/plegma_card.dart';

// ============================================================================
// GOVERNANÇA — Bloqueada até 10.000 nós ativos
// Regra: votação comunitária só é ativada quando a rede atingir 10k nós
// ============================================================================

class GovernancaScreen extends StatelessWidget {
  const GovernancaScreen({super.key});

  static const int _minimoNos = 10000;

  @override
  Widget build(BuildContext context) {
    final validator  = context.watch<ValidatorProvider>();
    final wallet     = context.watch<WalletProvider>();
    final nos        = validator.nosAtivos;
    final progresso  = (nos / _minimoNos).clamp(0.0, 1.0);
    final bloqueado  = nos < _minimoNos;
    final pesoVoto   = wallet.wallet?.pesoVoto   ?? 1.0;
    final categoria  = wallet.wallet?.categoria  ?? '';
    final plggTotal  = wallet.wallet?.plggTotal  ?? 0.0;
    final isSocio    = plggTotal > 0;

    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        title: const Text('GOVERNANÇA', style: TextStyle(letterSpacing: 3)),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: StatusBadge(
              label: bloqueado ? 'BLOQUEADO' : 'ATIVO',
              color: bloqueado ? PlegmaColors.amber : PlegmaColors.green,
            ),
          ),
        ],
      ),
      body: ListView(
        padding : const EdgeInsets.all(16),
        children: [

          // ── Banner de progresso ──
          PlegmaCard(
            topAccent  : bloqueado ? PlegmaColors.amber : PlegmaColors.green,
            borderColor: bloqueado
                ? PlegmaColors.amber.withValues(alpha: 0.3)
                : PlegmaColors.green.withValues(alpha: 0.3),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    PlegmaLabel(
                      bloqueado ? 'Aguardando Quórum' : 'Governança Ativa',
                      color: bloqueado ? PlegmaColors.amber : PlegmaColors.green,
                    ),
                    Text(
                      '${nos.toString()} / ${_minimoNos.toString()} nós',
                      style: const TextStyle(
                        fontSize: 11, color: PlegmaColors.textDim,
                        letterSpacing: 1,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value           : progresso,
                    minHeight       : 6,
                    backgroundColor : PlegmaColors.bg3,
                    color           : bloqueado
                        ? PlegmaColors.amber
                        : PlegmaColors.green,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  bloqueado
                      ? 'A votação comunitária será ativada quando a rede atingir '
                        '${_minimoNos.toString()} nós ativos. '
                        'Faltam ${(_minimoNos - nos).toString()} nós.'
                      : 'Quórum atingido. Governança comunitária ativa.',
                  style: const TextStyle(
                    fontSize: 12, color: PlegmaColors.textDim, height: 1.6,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Card Peso de Voto do usuário ──
          PlegmaCard(
            topAccent  : isSocio ? _categoriaColor(categoria) : PlegmaColors.textDim,
            borderColor: isSocio
                ? _categoriaColor(categoria).withValues(alpha: 0.3)
                : PlegmaColors.border,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                PlegmaLabel(
                  'Seu Peso de Voto',
                  color: isSocio ? _categoriaColor(categoria) : PlegmaColors.textDim,
                ),
                const SizedBox(height: 14),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      pesoVoto.toStringAsFixed(2),
                      style: TextStyle(
                        fontSize    : 36,
                        fontWeight  : FontWeight.bold,
                        color       : isSocio
                            ? _categoriaColor(categoria)
                            : PlegmaColors.textDim,
                        letterSpacing: 1,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Text(
                        '/ 5,0 máx',
                        style: const TextStyle(
                          fontSize: 12, color: PlegmaColors.textDim,
                        ),
                      ),
                    ),
                    const Spacer(),
                    if (isSocio)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color : _categoriaColor(categoria)
                              .withValues(alpha: 0.1),
                          border: Border.all(
                              color: _categoriaColor(categoria)
                                  .withValues(alpha: 0.4)),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          categoria,
                          style: TextStyle(
                            fontSize    : 10,
                            letterSpacing: 2,
                            color       : _categoriaColor(categoria),
                            fontWeight  : FontWeight.bold,
                          ),
                        ),
                      )
                    else
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color : PlegmaColors.bg3,
                          border: Border.all(color: PlegmaColors.border),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'NÓ COMUM',
                          style: TextStyle(
                            fontSize: 10, letterSpacing: 2,
                            color: PlegmaColors.textDim,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 10),
                // Barra de progresso do peso
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value          : ((pesoVoto - 1.0) / 4.0).clamp(0.0, 1.0),
                    minHeight      : 4,
                    backgroundColor: PlegmaColors.bg3,
                    color          : isSocio
                        ? _categoriaColor(categoria)
                        : PlegmaColors.textDim,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  isSocio
                      ? 'Peso proporcional ao seu saldo de ${plggTotal.toStringAsFixed(0)} PLG-G. '
                        'Escala: 1,01 (mín \$1) a 5,0 (máx \$1.000). '
                        'O peso segue o token — ao vender PLG-G, o peso é transferido.'
                      : 'Nós validadores sem PLG-G têm peso base 1,0. '
                        'Adquira PLG-G na Reserva Genesis para obter peso proporcional '
                        'de 1,01 a 5,0 no protocolo de governança.',
                  style: const TextStyle(
                    fontSize: 11, color: PlegmaColors.textDim, height: 1.6,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Regras de governança ──
          PlegmaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                PlegmaLabel('Regras de Governança — Estatuto'),
                SizedBox(height: 14),
                _RegraRow(
                  icone  : '📱',
                  titulo : 'Voto Exclusivo do Nó Móvel',
                  descricao: 'Apenas o dispositivo móvel com carteira Dilithium3 activa '
                      'pode assinar propostas e votar. PCs e servidores não têm '
                      'direito de voto — poder distribuído por indivíduos únicos.',
                ),
                Divider(color: PlegmaColors.border, height: 20),
                _RegraRow(
                  icone  : '🛡',
                  titulo : 'Proteção Sybil',
                  descricao: 'A assinatura Dilithium3 vinculada à carteira impede que um único '
                      'utilizador crie múltiplas instâncias de votação em servidores '
                      'virtuais.',
                ),
                Divider(color: PlegmaColors.border, height: 20),
                _RegraRow(
                  icone  : '⚖',
                  titulo : 'Justiça Algorítmica',
                  descricao: 'Potência de hardware não confere maior peso de '
                      'voto. Um celular simples tem o mesmo poder de voto que '
                      'um servidor de alta performance.',
                ),
                Divider(color: PlegmaColors.border, height: 20),
                _RegraRow(
                  icone  : '🔒',
                  titulo : 'Quórum Mínimo',
                  descricao: 'Nenhuma proposta pode ser votada sem 10.000 nós '
                      'ativos na rede. Garante representatividade antes de '
                      'qualquer mudança de parâmetros.',
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Propostas futuras (placeholder) ──
          PlegmaCard(
            borderColor: PlegmaColors.purple.withValues(alpha: 0.3),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const PlegmaLabel('Propostas — V2.0+',
                    color: PlegmaColors.purple),
                const SizedBox(height: 12),
                ...[
                  'Ajuste da taxa de decaimento de emissão',
                  'Parâmetros do protocolo de quarentena (60%)',
                  'Limites do Aerarium e emissão adaptativa',
                  'Atualização do compilador PlegmaScript',
                  'Integração de novos tipos de hardware',
                ].map((p) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    children: [
                      Container(
                        width : 6, height: 6,
                        decoration: const BoxDecoration(
                          color : PlegmaColors.purple,
                          shape : BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(p, style: const TextStyle(
                          fontSize: 12, color: PlegmaColors.textDim,
                        )),
                      ),
                      const Text(
                        'V2.0+',
                        style: TextStyle(
                          fontSize: 9, color: PlegmaColors.purple,
                          letterSpacing: 1,
                        ),
                      ),
                    ],
                  ),
                )),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // ── Botão bloqueado ──
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: null, // Desabilitado
              style: ElevatedButton.styleFrom(
                disabledBackgroundColor:
                    PlegmaColors.amber.withValues(alpha: 0.1),
                disabledForegroundColor: PlegmaColors.amber,
                side: BorderSide(
                  color: PlegmaColors.amber.withValues(alpha: 0.4),
                ),
              ),
              child: Text(
                bloqueado
                    ? 'BLOQUEADO — ${(_minimoNos - nos).toString()} NÓS RESTANTES'
                    : 'VER PROPOSTAS ATIVAS',
                style: const TextStyle(fontSize: 11, letterSpacing: 2),
              ),
            ),
          ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

Color _categoriaColor(String cat) {
  switch (cat) {
    case 'MASTER':    return PlegmaColors.amber;
    case 'SENTINELA': return PlegmaColors.cyan;
    default:          return PlegmaColors.green;
  }
}

class _RegraRow extends StatelessWidget {
  final String icone;
  final String titulo;
  final String descricao;

  const _RegraRow({
    required this.icone,
    required this.titulo,
    required this.descricao,
  });

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(icone, style: const TextStyle(fontSize: 18)),
      const SizedBox(width: 12),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo, style: const TextStyle(
              fontSize: 13, color: PlegmaColors.text,
              fontWeight: FontWeight.bold,
            )),
            const SizedBox(height: 4),
            Text(descricao, style: const TextStyle(
              fontSize: 11, color: PlegmaColors.textDim, height: 1.6,
            )),
          ],
        ),
      ),
    ],
  );
}
