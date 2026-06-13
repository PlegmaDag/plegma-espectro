import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'api_service.dart';
import 'crypto_service.dart';
import 'dilithium_ffi_service.dart';
import 'storage_service.dart';

// =============================================================================
// HEARTBEAT SERVICE — PLEGMA DAG
//
// Envia sinal de presença ao nó cada 2 minutos via POST /api/node/heartbeat.
// Assina o node_id com Dilithium3 — backend valida e regista em nos_rede.
// O nó aparece como VALIDATOR no console admin enquanto o heartbeat estiver ativo.
// =============================================================================

class HeartbeatService {
  HeartbeatService._();
  static final HeartbeatService instance = HeartbeatService._();

  static const _intervalo = Duration(minutes: 2);
  Timer? _timer;

  /// Inicia o heartbeat periódico (e envia o primeiro imediatamente).
  void start() {
    _timer?.cancel();
    _enviar();
    _timer = Timer.periodic(_intervalo, (_) => _enviar());
  }

  /// Para o heartbeat (ex: ao deslogar).
  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _enviar() async {
    try {
      final address   = await StorageService.lerEndereco();
      final privB64   = await StorageService.lerChavePrivada();
      final pubB64    = await StorageService.lerChavePublica();

      if (address == null || privB64 == null || pubB64 == null) return;

      final nodeId = 'VALIDATOR_$address';

      // Assina node_id com Dilithium3 — retorna Base64
      final sigB64 = await CryptoService.assinarNonce(nodeId, privB64);

      // Converte Base64 → hex (formato esperado pelo backend)
      final sigHex = DilithiumFfiService.bytesToHex(base64.decode(sigB64));
      final pubHex = DilithiumFfiService.bytesToHex(base64.decode(pubB64));

      await ApiService.nodeHeartbeat(
        nodeId,
        publicKey : pubHex,
        signature : sigHex,
        metadata  : {
          'node_type'  : 'VALIDATOR',
          'plg_address': address,
        },
      );
    } catch (e) {
      debugPrint('[HeartbeatService] erro: $e');
    }
  }
}
