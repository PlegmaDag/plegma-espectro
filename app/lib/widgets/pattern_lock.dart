import 'package:flutter/material.dart';

// ============================================================================
// PATTERN LOCK — Grade 3×3 de pontos com gesto de desenho
//
// onComplete(pattern) — chamado com string "0-1-4-7-8" quando ≥ 4 pontos
// onWrong()           — chamado quando o gesto tem < 4 pontos
// ============================================================================

class PatternLock extends StatefulWidget {
  final void Function(String pattern) onComplete;
  final void Function()? onWrong;
  final Color activeColor;
  final Color inactiveColor;

  const PatternLock({
    super.key,
    required this.onComplete,
    this.onWrong,
    this.activeColor   = const Color(0xFF00F2FF),
    this.inactiveColor = const Color(0xFF334155),
  });

  @override
  State<PatternLock> createState() => _PatternLockState();
}

class _PatternLockState extends State<PatternLock> {
  static const int    _n    = 3;
  static const double _size = 240.0;
  static const double _cell = _size / _n;
  static const double _hitR = _cell * 0.38; // raio de detecção de toque

  late final List<Offset> _centers;
  final List<int> _path = [];
  Offset?         _finger;
  bool            _done = false;

  @override
  void initState() {
    super.initState();
    _centers = [
      for (int r = 0; r < _n; r++)
        for (int c = 0; c < _n; c++)
          Offset(c * _cell + _cell / 2, r * _cell + _cell / 2),
    ];
  }

  int? _hitDot(Offset pos) {
    for (int i = 0; i < _centers.length; i++) {
      if (_path.contains(i)) continue;
      if ((_centers[i] - pos).distance < _hitR) return i;
    }
    return null;
  }

  void _start(Offset pos) {
    if (_done) return;
    setState(() { _path.clear(); _finger = pos; });
    final h = _hitDot(pos);
    if (h != null) setState(() => _path.add(h));
  }

  void _move(Offset pos) {
    if (_done) return;
    setState(() => _finger = pos);
    final h = _hitDot(pos);
    if (h != null) setState(() => _path.add(h));
  }

  void _end() {
    if (_done) return;
    setState(() => _finger = null);
    if (_path.length >= 4) {
      setState(() => _done = true);
      final pattern = _path.join('-');
      Future.delayed(const Duration(milliseconds: 350), () {
        if (mounted) setState(() { _path.clear(); _done = false; });
      });
      widget.onComplete(pattern);
    } else {
      widget.onWrong?.call();
      Future.delayed(const Duration(milliseconds: 350), () {
        if (mounted) setState(() { _path.clear(); });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onPanStart : (d) => _start(d.localPosition),
      onPanUpdate: (d) => _move(d.localPosition),
      onPanEnd   : (_) => _end(),
      child: CustomPaint(
        size   : const Size(_size, _size),
        painter: _PatternPainter(
          centers    : _centers,
          path       : _path,
          finger     : _finger,
          done       : _done,
          activeColor: widget.activeColor,
          inactColor : widget.inactiveColor,
          hitR       : _hitR,
        ),
      ),
    );
  }
}

// ── Painter ──────────────────────────────────────────────────────────────────
class _PatternPainter extends CustomPainter {
  final List<Offset> centers;
  final List<int>    path;
  final Offset?      finger;
  final bool         done;
  final Color        activeColor;
  final Color        inactColor;
  final double       hitR;

  const _PatternPainter({
    required this.centers,
    required this.path,
    required this.finger,
    required this.done,
    required this.activeColor,
    required this.inactColor,
    required this.hitR,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color      = activeColor.withOpacity(0.55)
      ..strokeWidth = 1.8
      ..style      = PaintingStyle.stroke;

    // Linhas entre pontos selecionados
    for (int i = 1; i < path.length; i++) {
      canvas.drawLine(centers[path[i - 1]], centers[path[i]], linePaint);
    }

    // Linha até a posição atual do dedo
    if (path.isNotEmpty && finger != null && !done) {
      canvas.drawLine(centers[path.last], finger!, linePaint);
    }

    // Pontos
    for (int i = 0; i < centers.length; i++) {
      final sel   = path.contains(i);
      final color = sel ? activeColor : inactColor;

      // anel externo
      canvas.drawCircle(
        centers[i], hitR * 0.52,
        Paint()
          ..color      = color.withOpacity(sel ? 0.18 : 0.1)
          ..style      = PaintingStyle.fill,
      );
      canvas.drawCircle(
        centers[i], hitR * 0.52,
        Paint()
          ..color      = color.withOpacity(sel ? 0.6 : 0.35)
          ..strokeWidth = 1.2
          ..style      = PaintingStyle.stroke,
      );

      // ponto central
      canvas.drawCircle(
        centers[i], hitR * 0.20,
        Paint()..color = color..style = PaintingStyle.fill,
      );
    }
  }

  @override
  bool shouldRepaint(_PatternPainter o) => true;
}
