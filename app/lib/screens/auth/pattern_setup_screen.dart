import 'package:flutter/material.dart';
import '../../services/auth_service.dart';
import '../../theme/plegma_theme.dart';
import '../../widgets/pattern_lock.dart';

// ============================================================================
// PATTERN SETUP SCREEN — Configuração do padrão secreto (B2)
// Exibida apenas no primeiro boot, após criação da carteira.
// Três passos: info (leitura obrigatória + checkbox) → draw1 → draw2.
// ============================================================================

enum _SetupFase { info, draw1, draw2 }

class PatternSetupScreen extends StatefulWidget {
  const PatternSetupScreen({super.key});

  @override
  State<PatternSetupScreen> createState() => _PatternSetupScreenState();
}

class _PatternSetupScreenState extends State<PatternSetupScreen> {
  _SetupFase _fase       = _SetupFase.info;
  String?    _first;
  bool       _mismatch   = false;
  bool       _leuAviso   = false; // checkbox obrigatório

  Future<void> _onPattern(String pattern) async {
    if (_fase == _SetupFase.draw1) {
      setState(() {
        _first    = pattern;
        _fase     = _SetupFase.draw2;
        _mismatch = false;
      });
    } else {
      if (pattern == _first) {
        await AuthService.savePattern(pattern);
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, '/home');
      } else {
        setState(() { _mismatch = true; _fase = _SetupFase.draw1; _first = null; });
        await Future.delayed(const Duration(seconds: 2));
        if (mounted) setState(() => _mismatch = false);
      }
    }
  }

  // ── Tela de aviso obrigatório ─────────────────────────────────────────────
  Widget _buildInfo() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [

        const Icon(Icons.shield_outlined, color: PlegmaColors.cyan, size: 44),
        const SizedBox(height: 20),

        const Text(
          'COMO FUNCIONA A\nAUTENTICAÇÃO PLEGMA',
          style: TextStyle(
            fontSize     : 14,
            color        : PlegmaColors.text,
            fontWeight   : FontWeight.bold,
            letterSpacing: 2,
            height       : 1.5,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 28),

        // Bloco 1 — digital
        _infoBloco(
          icon  : Icons.fingerprint,
          cor   : PlegmaColors.cyan,
          titulo: 'PASSO 1 — DIGITAL',
          texto : 'Ao abrir o app, a digital (ou reconhecimento facial) é pedida automaticamente. '
                  'Ela desbloqueia apenas uma parte do app — a tela fica neutra, sem opções visíveis.',
        ),

        const SizedBox(height: 14),

        // Bloco 2 — padrão secreto
        _infoBloco(
          icon  : Icons.grid_view_rounded,
          cor   : PlegmaColors.amber,
          titulo: 'PASSO 2 — PADRÃO SECRETO',
          texto : 'Para desbloquear totalmente, toque 3 vezes rapidamente no logo PLEGMA. '
                  'A grade de pontos vai aparecer para você desenhar o padrão.\n\n'
                  'Nenhuma indicação aparece na tela — só você saberá que esse segundo passo existe.',
        ),

        const SizedBox(height: 14),

        // Bloco 3 — anti-coação
        _infoBloco(
          icon  : Icons.security,
          cor   : PlegmaColors.green,
          titulo: 'PROTEÇÃO ANTI-COAÇÃO',
          texto : 'Se alguém forçar você a abrir o app, use apenas a digital. '
                  'O app parecerá desbloqueado mas nenhuma transação será possível. '
                  'A outra pessoa não saberá que existe um segundo passo.',
        ),

        const SizedBox(height: 28),

        // Checkbox obrigatório
        GestureDetector(
          onTap: () => setState(() => _leuAviso = !_leuAviso),
          child: Container(
            padding   : const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color : _leuAviso
                  ? PlegmaColors.cyan.withValues(alpha: 0.07)
                  : PlegmaColors.red.withValues(alpha: 0.05),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: _leuAviso
                    ? PlegmaColors.cyan.withValues(alpha: 0.4)
                    : PlegmaColors.red.withValues(alpha: 0.3),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  _leuAviso
                      ? Icons.check_box
                      : Icons.check_box_outline_blank,
                  color: _leuAviso ? PlegmaColors.cyan : PlegmaColors.textDim,
                  size: 22,
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    'Entendi que a digital sozinha não desbloqueia o app completamente. '
                    'Para acessar tudo, vou tocar 3× no logo e desenhar meu padrão.',
                    style: TextStyle(
                      fontSize     : 11,
                      color        : PlegmaColors.textDim,
                      height       : 1.6,
                      letterSpacing: 0.3,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 20),

        // Botão — só ativa após checkbox
        GestureDetector(
          onTap: _leuAviso
              ? () => setState(() => _fase = _SetupFase.draw1)
              : null,
          child: AnimatedContainer(
            duration  : const Duration(milliseconds: 200),
            width     : double.infinity,
            padding   : const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              color       : _leuAviso
                  ? PlegmaColors.cyan
                  : PlegmaColors.textDim.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              'CONFIGURAR MEU PADRÃO',
              style: TextStyle(
                fontSize     : 12,
                fontWeight   : FontWeight.bold,
                letterSpacing: 2,
                color        : _leuAviso ? Colors.black : PlegmaColors.textDim,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ),

        if (!_leuAviso) ...[
          const SizedBox(height: 10),
          const Text(
            'Marque a caixa acima para continuar.',
            style: TextStyle(
              fontSize     : 10,
              color        : PlegmaColors.red,
              letterSpacing: 0.5,
            ),
            textAlign: TextAlign.center,
          ),
        ],

      ],
    );
  }

  Widget _infoBloco({
    required IconData icon,
    required Color    cor,
    required String   titulo,
    required String   texto,
  }) {
    return Container(
      padding   : const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color       : cor.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border      : Border.all(color: cor.withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: cor, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  titulo,
                  style: TextStyle(
                    fontSize     : 10,
                    color        : cor,
                    fontWeight   : FontWeight.bold,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  texto,
                  style: const TextStyle(
                    fontSize     : 11,
                    color        : PlegmaColors.textDim,
                    height       : 1.6,
                    letterSpacing: 0.3,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Tela de desenho do padrão ─────────────────────────────────────────────
  Widget _buildDraw() {
    final isDraw1 = _fase == _SetupFase.draw1;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [

        const Icon(Icons.grid_view_rounded,
            color: PlegmaColors.cyan, size: 36),
        const SizedBox(height: 20),

        Text(
          isDraw1 ? 'DEFINA SEU PADRÃO SECRETO' : 'CONFIRME O PADRÃO',
          style: const TextStyle(
            fontSize     : 14,
            color        : PlegmaColors.text,
            fontWeight   : FontWeight.bold,
            letterSpacing: 2,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 10),

        Text(
          isDraw1
              ? 'Mínimo de 4 pontos. Não há recuperação — memorize.'
              : 'Desenhe o mesmo padrão novamente para confirmar.',
          style: const TextStyle(
            fontSize     : 11,
            color        : PlegmaColors.textDim,
            letterSpacing: 0.5,
            height       : 1.6,
          ),
          textAlign: TextAlign.center,
        ),

        const SizedBox(height: 40),

        PatternLock(onComplete: _onPattern),

        const SizedBox(height: 24),

        if (_mismatch)
          const Text(
            'Padrões não coincidem. Comece novamente.',
            style: TextStyle(
              fontSize     : 11,
              color        : PlegmaColors.red,
              letterSpacing: 1,
            ),
            textAlign: TextAlign.center,
          ),

      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: _fase == _SetupFase.info ? _buildInfo() : _buildDraw(),
        ),
      ),
    );
  }
}
