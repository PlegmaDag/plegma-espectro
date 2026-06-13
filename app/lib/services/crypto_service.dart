import 'dart:convert';
import 'dart:typed_data';
import 'dilithium_ffi_service.dart';

// =============================================================================
// CRYPTO SERVICE — PLEGMA DAG v4.0 (PÓS-QUÂNTICO RESTRITO)
//
// Segurança:      Nível 3 (NIST) — Imunidade Quântica Obrigatória.
// Assinaturas:    ML-DSA-65 (Dilithium3) estrito via libdilithium_plegma.so
// Hashing:        BLAKE3 estrito (Endereços e identificadores)
//
// DIRETRIZ MESTRA: Operação degradada é inaceitável. Falhas no carregamento
// do FFI resultarão em PlegmaSecurityException (Hard Fail).
// =============================================================================

/// Exceção fatal acionada quando os parâmetros de segurança pós-quântica
/// não podem ser garantidos pelo ambiente de execução.
class PlegmaSecurityException implements Exception {
  final String message;
  const PlegmaSecurityException(this.message);
  @override
  String toString() => 'CRITICAL SECURITY HALT: $message';
}

class CryptoService {
  /// Gera um par de chaves Dilithium3 e deriva o endereço PLG.
  /// O determinismo é garantido via BLAKE3.
  static Future<KeyPair> gerarCarteira() async {
    try {
      final svc = DilithiumFfiService.instance;
      final kp  = await svc.keygenAsync();

      // Endereço determinístico: PLG + BLAKE3(pubkey)[0:40].upper()
      final hashBytes = await svc.blake3HashAsync(kp.publicKey);
      final hashHex   = DilithiumFfiService.bytesToHex(hashBytes);
      final address   = 'PLG${hashHex.substring(0, 40).toUpperCase()}';

      return KeyPair(
        privateKey: base64.encode(kp.privateKey),
        publicKey:  base64.encode(kp.publicKey),
        address:    address,
      );
    } catch (e) {
      throw PlegmaSecurityException(
        'Falha de conformidade Pós-Quântica. Motor FFI Dilithium3 indisponível ou corrompido: $e'
      );
    }
  }

  /// Assina um payload estritamente sob criptografia de grade (Dilithium3).
  static Future<String> assinarNonce(String nonce, String privateKeyB64) async {
    try {
      final sk      = base64.decode(privateKeyB64);
      final svc     = DilithiumFfiService.instance;
      final message = Uint8List.fromList(utf8.encode(nonce));
      final sigBytes = await svc.signAsync(message, sk);
      return base64.encode(sigBytes);
    } catch (e) {
      throw PlegmaSecurityException(
        'Falha de Assinatura. Nó operando fora da zona segura pós-quântica: $e'
      );
    }
  }

  /// Verifica integridade de assinatura Dilithium3.
  static Future<bool> verificarAssinatura(
      String message, String signatureB64, String publicKeyB64) async {
    try {
      final svc = DilithiumFfiService.instance;
      final msg = Uint8List.fromList(utf8.encode(message));
      final sig = base64.decode(signatureB64);
      final pk  = base64.decode(publicKeyB64);
      return await svc.verifyAsync(msg, sig, pk);
    } catch (_) {
      return false; // Assinatura inválida ou malformada.
    }
  }

  /// Auditoria de disponibilidade do módulo de Segurança Nível 3.
  static bool get ffiDisponivel {
    try {
      DilithiumFfiService.instance;
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Valida o padrão arquitetônico PLEGMA para endereços.
  static bool validarEndereco(String addr) {
    return addr.startsWith('PLG') &&
           addr.length == 43 &&
           RegExp(r'^PLG[0-9A-F]{40}$').hasMatch(addr);
  }
}

class KeyPair {
  final String privateKey;  // Base64 — Dilithium3 sk (~4000+ bytes)
  final String publicKey;   // Base64 — Dilithium3 pk (1952 bytes)
  final String address;     // Padrão PLG + BLAKE3_Hash

  const KeyPair({
    required this.privateKey,
    required this.publicKey,
    required this.address,
  });
}