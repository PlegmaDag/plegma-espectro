import 'dart:typed_data';

// ============================================================
// DilithiumFfiService — stub para análise estática (CI)
// A implementação real usa FFI nativo (libdilithium_plegma.so)
// e é carregada em runtime via plugin de plataforma.
// ============================================================

class _KeyPair {
  final Uint8List publicKey;
  final Uint8List privateKey;
  const _KeyPair({required this.publicKey, required this.privateKey});
}

class DilithiumFfiService {
  DilithiumFfiService._();
  static final DilithiumFfiService instance = DilithiumFfiService._();

  /// Gera um par de chaves Dilithium3 (ML-DSA-65).
  Future<_KeyPair> keygenAsync() async {
    throw UnimplementedError('DilithiumFfiService: FFI nativo não carregado.');
  }

  /// Calcula BLAKE3 de [data] e retorna o hash como Uint8List.
  Future<Uint8List> blake3HashAsync(Uint8List data) async {
    throw UnimplementedError('DilithiumFfiService: FFI nativo não carregado.');
  }

  /// Assina [message] com a chave secreta [sk].
  Future<Uint8List> signAsync(Uint8List message, Uint8List sk) async {
    throw UnimplementedError('DilithiumFfiService: FFI nativo não carregado.');
  }

  /// Verifica [signature] sobre [message] com a chave pública [pk].
  Future<bool> verifyAsync(Uint8List message, Uint8List signature, Uint8List pk) async {
    throw UnimplementedError('DilithiumFfiService: FFI nativo não carregado.');
  }

  // Alias usado em alguns serviços
  Future<bool> verificarAssincrono(Uint8List msg, Uint8List sig, Uint8List pk) =>
      verifyAsync(msg, sig, pk);

  /// Converte bytes para string hexadecimal.
  static String bytesToHexadecimal(Uint8List bytes) {
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }
}
