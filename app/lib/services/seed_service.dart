
// ============================================================
// SeedService — stub para análise estática (CI)
// Gestão de frase semente e derivação de carteira.
// ============================================================

class SeedService {
  SeedService._();
  static final SeedService instance = SeedService._();

  /// Gera uma nova frase semente (12 palavras).
  static Future<List<String>> gerar() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Lê a frase semente armazenada.
  static Future<List<String>?> ler() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Salva a frase semente.
  static Future<void> salvar(List<String> mnemonic) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Encripta ou decripta uma chave com a frase semente.
  static Future<dynamic> encriptarOuDecriptarChave(dynamic chave, [dynamic extra]) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Verifica se foi realizado backup da frase semente.
  static Future<bool> backupFeito() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Envia backup ZK da frase semente.
  static Future<void> enviarZkBackup({String? plgAddress, List<String>? words}) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Verifica se existe frase semente armazenada.
  static Future<bool> hasMnemonic() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Remove a frase semente armazenada.
  static Future<void> clearMnemonic() async {
    throw UnimplementedError('SeedService: não implementado.');
  }
}
