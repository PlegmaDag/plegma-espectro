import 'package:flutter/material.dart';
import '../theme/plegma_theme.dart';

// ============================================================================
// PLEGMA WIDGETS — Componentes reutilizáveis
// ============================================================================

/// Card com borda ciano e fundo escuro
class PlegmaCard extends StatelessWidget {
  final Widget child;
  final EdgeInsets? padding;
  final Color?  borderColor;
  final Color?  topAccent;
  final VoidCallback? onTap;

  const PlegmaCard({
    super.key,
    required this.child,
    this.padding,
    this.borderColor,
    this.topAccent,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color       : PlegmaColors.bg2,
          borderRadius: BorderRadius.circular(16),
          border      : Border.all(
            color : borderColor ?? PlegmaColors.border,
            width : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize      : MainAxisSize.min,
          children          : [
            if (topAccent != null)
              Container(
                height          : 2,
                decoration      : BoxDecoration(
                  color         : topAccent,
                  borderRadius  : const BorderRadius.vertical(
                    top: Radius.circular(16),
                  ),
                ),
              ),
            Padding(
              padding : padding ?? const EdgeInsets.all(16),
              child   : child,
            ),
          ],
        ),
      ),
    );
  }
}

/// Label pequeno estilo dashboard
class PlegmaLabel extends StatelessWidget {
  final String text;
  final Color? color;

  const PlegmaLabel(this.text, {super.key, this.color});

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: TextStyle(
        fontSize      : 10,
        letterSpacing : 2,
        color         : color ?? PlegmaColors.textDim,
        fontWeight    : FontWeight.w400,
      ),
    );
  }
}

/// Valor grande com cor
class PlegmaValue extends StatelessWidget {
  final String text;
  final Color? color;
  final double fontSize;

  const PlegmaValue(
    this.text, {
    super.key,
    this.color,
    this.fontSize = 20,
  });

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        fontSize  : fontSize,
        color     : color ?? PlegmaColors.text,
        fontWeight: FontWeight.bold,
        letterSpacing: 0.5,
      ),
    );
  }
}

/// Badge de status
class StatusBadge extends StatelessWidget {
  final String label;
  final Color  color;
  final bool   pulsing;

  const StatusBadge({
    super.key,
    required this.label,
    required this.color,
    this.pulsing = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding     : const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration  : BoxDecoration(
        color         : color.withValues(alpha: 0.1),
        borderRadius  : BorderRadius.circular(4),
        border        : Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children    : [
          Container(
            width         : 6,
            height        : 6,
            decoration    : BoxDecoration(
              color         : color,
              shape         : BoxShape.circle,
              boxShadow     : [BoxShadow(color: color.withValues(alpha: 0.6), blurRadius: 4)],
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize      : 10,
              color         : color,
              letterSpacing : 1.5,
              fontWeight    : FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}

/// Linha de divider com label
class PlegmaDivider extends StatelessWidget {
  final String? label;
  const PlegmaDivider({super.key, this.label});

  @override
  Widget build(BuildContext context) {
    if (label == null) {
      return const Divider(color: PlegmaColors.border, thickness: 1, height: 24);
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          const Expanded(child: Divider(color: PlegmaColors.border, thickness: 1)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              label!.toUpperCase(),
              style: const TextStyle(
                fontSize: 9, letterSpacing: 2, color: PlegmaColors.textDim,
              ),
            ),
          ),
          const Expanded(child: Divider(color: PlegmaColors.border, thickness: 1)),
        ],
      ),
    );
  }
}

/// Formata valor PLG
String fmtPlg(double v) =>
    '${v.toStringAsFixed(4)} \$PLG';

/// Formata valor USDT
String fmtUsdt(double v) =>
    '\$ ${v.toStringAsFixed(2)}';
