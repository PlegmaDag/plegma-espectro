// ============================================================
// SeedService — stub para análise estática (CI)
// Gestão de frase semente (BIP-39 / derivação de carteira).
// ============================================================

class SeedService {
  SeedService._();
  static final SeedService instance = SeedService._();

  /// Gera uma nova frase semente (12 ou 24 palavras).
  Future<List<String>> generateMnemonic({int strength = 128}) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Valida uma frase semente.
  bool validateMnemonic(List<String> words) {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Deriva a chave privada a partir da frase semente.
  Future<String> derivePrivateKey(List<String> mnemonic) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Armazena a frase semente de forma segura.
  Future<void> storeMnemonic(List<String> mnemonic) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Recupera a frase semente armazenada.
  Future<List<String>?> retrieveMnemonic() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Verifica se existe frase semente armazenada.
  Future<bool> hasMnemonic() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Remove a frase semente armazenada.
  Future<void> clearMnemonic() async {
    throw UnimplementedError('SeedService: não implementado.');
  }
}
