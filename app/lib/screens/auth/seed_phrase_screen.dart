import 'package:flutter/material.dart';

// ============================================================
// SeedPhraseScreen — stub para análise estática (CI)
// Tela de exibição e configuração da frase semente.
// ============================================================

class SeedPhraseScreen extends StatelessWidget {
  final List<String> words;
  final String plgAddress;

  const SeedPhraseScreen({
    super.key,
    required this.words,
    required this.plgAddress,
  });

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Text('SeedPhraseScreen — not implemented'),
      ),
    );
  }
}
