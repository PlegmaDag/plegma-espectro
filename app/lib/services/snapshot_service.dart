import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/services.dart';

import 'api_service.dart';
import 'storage_service.dart';
import 'dilithium_ffi_service.dart';

// ============================================================================
// SNAPSHOT SERVICE — Integridade ZK do Dispositivo
//
// Arquitetura:
//   1. Na instalação: tira snapshot dos apps instalados (list + cert_hashes)
//   2. Computa state_hash = BLAKE3(sorted app list) — 100% local
//   3. Ancora na rede: POST /shield/anchor → recebe ZK proof + anchor_id
//   4. Armazena {state_hash, zk_proof, anchor_id, apps} localmente
//
//   Monitoramento contínuo via EventChannel (BroadcastReceiver Android):
//   - PACKAGE_ADDED / PACKAGE_REMOVED / PACKAGE_CHANGED disparam evento
//   - Flutter re-lê apps, recomputa hash, compara com snapshot
//   - Se diferente: persiste delta, exibe alerta ao usuário
//   - ZERO tráfego de rede no monitoramento — só no snapshot inicial
// ============================================================================

const _kShieldChannel   = MethodChannel('com.plegmadag.app/shield');
const _kPackageEvents   = EventChannel('com.plegmadag.app/package_events');

// Resultado de criação de snapshot
class SnapshotResult {
  final bool   sucesso;
  final String stateHash;
  final String anchorId;
  final String zkEngine;
  final int    appCount;
  final String? erro;

  const SnapshotResult({
    required this.sucesso,
    required this.stateHash,
    required this.anchorId,
    required this.zkEngine,
    required this.appCount,
    this.erro,
  });

  factory SnapshotResult.erro(String msg) => SnapshotResult(
    sucesso: false, stateHash: '', anchorId: '', zkEngine: '', appCount: 0, erro: msg,
  );
}

// Delta entre snapshot atual e novo estado
class SnapshotDelta {
  final List<String> adicionados;   // packages novos
  final List<String> removidos;     // packages que sumiram
  final List<String> alterados;     // cert_hash mudou (app re-assinado)
  final String       novoHash;

  const SnapshotDelta({
    required this.adicionados,
    required this.removidos,
    required this.alterados,
    required this.novoHash,
  });

  bool get temMudancas => adicionados.isNotEmpty || removidos.isNotEmpty || alterados.isNotEmpty;

  int get totalMudancas => adicionados.length + removidos.length + alterados.length;
}

class SnapshotService {

  // ── Leitura de apps via MethodChannel ──────────────────────────────────────

  static Future<List<Map<String, String>>> _lerApps() async {
    try {
      // Timeout de 15s: getInstalledPackages(GET_SIGNING_CERTIFICATES) pode
      // demorar em dispositivos com muitos apps instalados.
      final raw = await _kShieldChannel
          .invokeMethod('getInstalledApps')
          .timeout(const Duration(seconds: 15));
      return (raw as List)
          .map((e) => Map<String, String>.from(
              (e as Map).map((k, v) => MapEntry(k.toString(), v.toString()))))
          .toList();
    } on PlatformException {
      return [];
    } catch (_) {
      // Timeout ou outro erro — retorna lista vazia (snapshot adiado)
      return [];
    }
  }

  // ── Cálculo do state_hash ─────────────────────────────────────────────────
  // Determinístico: HASH(sorted "pkg\x00cert_hash\n" lines)
  //
  // Separador entre package_name e cert_hash: \x00 (null byte).
  // Motivo: ":" era ambíguo — um pacote chamado "com.a:b" com cert "c"
  // gerava o mesmo payload que "com.a" com cert "b:c" (colisão confirmada).
  // Package names (RFC) e cert hashes (hex) nunca contêm null bytes,
  // portanto \x00 é um separador não-ambíguo e sem colisão possível.
  //
  // Algoritmo: BLAKE3 — Hegemonia. SHA-256 e SHA3 expurgados.
  //   1. BLAKE3 via MethodChannel Android (caminho principal)
  //   2. BLAKE3 via FFI nativo (DilithiumFfiService) se MethodChannel falhar

  static Future<String> calcularHash(List<Map<String, String>> apps) async {
    final sorted = [...apps]
      ..sort((a, b) => (a['package_name'] ?? '').compareTo(b['package_name'] ?? ''));
    final payload = sorted
        .map((a) => '${a['package_name']}\x00${a['cert_hash']}')
        .join('\n');

    try {
      final hash = await _kShieldChannel.invokeMethod<String>(
          'computeStateHash', payload);
      if (hash != null && hash.isNotEmpty) return hash;
    } on PlatformException {
      // MethodChannel indisponível — cai no FFI BLAKE3 abaixo
    }

    // Fallback FFI: BLAKE3 nativo via libdilithium_plegma.so
    final bytes = Uint8List.fromList(utf8.encode(payload));
    final hash  = await DilithiumFfiService.instance.blake3HashAsync(bytes);
    return DilithiumFfiService.bytesToHex(hash);
  }

  // ── Criar snapshot inicial ────────────────────────────────────────────────

  static Future<SnapshotResult> criarSnapshot(String plgAddress) async {
    // 1. Lê apps instalados
    final apps = await _lerApps();
    if (apps.isEmpty) {
      return SnapshotResult.erro('Nenhum app de terceiros encontrado');
    }

    // 2. Computa hash local (BLAKE3 via MethodChannel ou FFI)
    final stateHash = await calcularHash(apps);

    // 3. Ancora na rede (envia APENAS hash, nunca a lista)
    final resp = await ApiService.shieldAnchor(
      stateHash  : stateHash,
      plgAddress : plgAddress,
      appCount   : apps.length,
    );

    // Fallback offline: gera anchor_id local se servidor indisponível
    final anchorId = resp?['anchor_id'] as String?
        ?? 'LOCAL-${DateTime.now().millisecondsSinceEpoch}';
    final zkEngine = resp?['zk_engine'] as String? ?? 'offline';
    final zkProof  = resp?['zk_proof']  as String? ?? '';

    // 4. Persiste localmente {hash, anchor, apps}
    await StorageService.salvarSnapshot({
      'state_hash'  : stateHash,
      'anchor_id'   : anchorId,
      'zk_proof'    : zkProof,
      'zk_engine'   : zkEngine,
      'app_count'   : apps.length,
      'timestamp'   : DateTime.now().millisecondsSinceEpoch,
      'plg_address' : plgAddress,
      // Lista usada apenas para diff local — nunca sai do dispositivo
      'apps': apps.map((a) => {
        'p': a['package_name'] ?? '',
        'c': a['cert_hash'] ?? '',
      }).toList(),
    });

    await StorageService.limparDeltaPendente();

    return SnapshotResult(
      sucesso  : true,
      stateHash: stateHash,
      anchorId : anchorId,
      zkEngine : zkEngine,
      appCount : apps.length,
    );
  }

  // ── Verificar delta contra snapshot armazenado ────────────────────────────

  static Future<SnapshotDelta?> verificarDelta() async {
    final snapshot = await StorageService.lerSnapshot();
    if (snapshot == null) return null;

    final apps = await _lerApps();
    if (apps.isEmpty) return null;

    final novoHash = await calcularHash(apps);
    final hashAntigo = snapshot['state_hash'] as String? ?? '';

    if (novoHash == hashAntigo) return null; // nenhuma mudança

    // Constrói mapa antigo
    final List<dynamic> rawApps = snapshot['apps'] as List? ?? [];
    final Map<String, String> appsAntigos = {
      for (final a in rawApps)
        (a['p'] as String): (a['c'] as String? ?? ''),
    };

    // Constrói mapa novo
    final Map<String, String> appsNovos = {
      for (final a in apps)
        (a['package_name'] ?? ''): (a['cert_hash'] ?? ''),
    };

    final adicionados = appsNovos.keys
        .where((pkg) => !appsAntigos.containsKey(pkg))
        .toList();

    final removidos = appsAntigos.keys
        .where((pkg) => !appsNovos.containsKey(pkg))
        .toList();

    final alterados = appsNovos.keys
        .where((pkg) =>
            appsAntigos.containsKey(pkg) &&
            appsAntigos[pkg] != appsNovos[pkg])
        .toList();

    return SnapshotDelta(
      adicionados: adicionados,
      removidos  : removidos,
      alterados  : alterados,
      novoHash   : novoHash,
    );
  }

  // ── Aprovar novo estado (re-ancoragem) ────────────────────────────────────

  static Future<SnapshotResult> aprovarEstado(String plgAddress) async {
    await StorageService.limparDeltaPendente();
    return criarSnapshot(plgAddress);
  }

  // ── Stream de eventos de pacotes (BroadcastReceiver Android) ─────────────
  // Cada evento: {action: "ADDED"|"REMOVED"|"CHANGED", package: "com.x"}

  static Stream<Map<String, String>> get packageChangeStream =>
      _kPackageEvents
          .receiveBroadcastStream()
          .map((e) => Map<String, String>.from(
              (e as Map).map((k, v) => MapEntry(k.toString(), v.toString()))));
}
