import 'dart:typed_data';

// ============================================================
// SeedService — stub para análise estática (CI)
// Gestão de frase semente e derivação de carteira.
// ============================================================

class SeedService {
  SeedService._();
  static final SeedService instance = SeedService._();

  /// Gera uma nova frase semente (12 palavras).
  Future<List<String>> gerar() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Lê a frase semente armazenada.
  Future<List<String>?> ler() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Salva a frase semente.
  Future<void> salvar(List<String> mnemonic) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Encripta ou decripta uma chave com a frase semente.
  Future<Uint8List> encriptarOuDecriptarChave(Uint8List chave, {bool encriptar = true}) async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Verifica se foi realizado backup da frase semente.
  Future<bool> backupFeito() async {
    throw UnimplementedError('SeedService: não implementado.');
  }

  /// Envia backup ZK da frase semente.
  Future<void> enviarZkBackup() async {
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
