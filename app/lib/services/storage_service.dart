import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ============================================================================
// STORAGE SERVICE — Armazenamento local seguro
//
// Estratégia dual-backend para máxima robustez em Android:
//   _storageA (encryptedSharedPreferences: false) — Keystore directo
//   _storageB (encryptedSharedPreferences: true)  — EncryptedSharedPreferences
//
// Escrita: ambos os backends em paralelo (um pode falhar silenciosamente).
// Leitura: tenta A com retry, fallback para B, fallback para SharedPreferences
//          (apenas para endereço — dado público).
//
// Motivo do dual-backend:
//   _storageA pode não persistir em certos dispositivos/versões Android.
//   _storageB perde dados após update de APK (sideload sem assinatura igual).
//   Com ambos activos, ao menos um sobrevive em cada cenário.
// ============================================================================

class StorageService {
  // Backend A — Keystore directo (mais estável em updates de APK)
  static const _storageA = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: false),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  // Backend B — EncryptedSharedPreferences (fallback; perde dados em APK update)
  static const _storageB = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  // Escreve nos dois backends; ignora falha individual silenciosamente.
  static Future<void> _escrever(String key, String value) async {
    try { await _storageA.write(key: key, value: value); } catch (_) {}
    try { await _storageB.write(key: key, value: value); } catch (_) {}
  }

  // Lê com retry de A; se todos falharem, tenta B.
  static Future<String?> _ler(String key) async {
    for (int i = 0; i < 3; i++) {
      try {
        final v = await _storageA.read(key: key);
        if (v != null && v.isNotEmpty) return v;
      } catch (_) {}
      if (i < 2) await Future.delayed(const Duration(milliseconds: 300));
    }
    try {
      final v = await _storageB.read(key: key);
      if (v != null && v.isNotEmpty) return v;
    } catch (_) {}
    return null;
  }

  // ── Chave privada (NUNCA sai do dispositivo) ───────────────────────────────
  static Future<void> salvarChavePrivada(String key) => _escrever('plg_private_key', key);
  static Future<String?> lerChavePrivada()            => _ler('plg_private_key');

  // ── Chave pública ─────────────────────────────────────────────────────────
  static Future<void> salvarChavePublica(String key) => _escrever('plg_public_key', key);
  static Future<String?> lerChavePublica()            => _ler('plg_public_key');

  // ── Endereço PLG ──────────────────────────────────────────────────────────
  // Espelhado também em SharedPreferences (dado público — terceira camada).
  static Future<void> salvarEndereco(String addr) async {
    await _escrever('plg_address', addr);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('plg_address_pub', addr);
    } catch (_) {}
  }

  static Future<String?> lerEndereco() async {
    final v = await _ler('plg_address');
    if (v != null && v.startsWith('PLG')) return v;
    // Terceira camada: SharedPreferences público
    try {
      final prefs = await SharedPreferences.getInstance();
      final backup = prefs.getString('plg_address_pub');
      if (backup != null && backup.startsWith('PLG')) return backup;
    } catch (_) {}
    return null;
  }

  // ── Sessão de autenticação ────────────────────────────────────────────────
  static Future<void> salvarSessao(String token) => _escrever('plg_session_token', token);

  static Future<String?> lerSessao() => _ler('plg_session_token');

  static Future<void> limparSessao() async {
    try { await _storageA.delete(key: 'plg_session_token'); } catch (_) {}
    try { await _storageB.delete(key: 'plg_session_token'); } catch (_) {}
  }

  // ── Carteira configurada? ─────────────────────────────────────────────────
  static Future<bool> carteiraConfigurada() async {
    final addr = await lerEndereco();
    if (addr == null || !addr.startsWith('PLG')) return false;
    final priv = await lerChavePrivada();
    return priv != null && priv.isNotEmpty;
  }

  // ── Preferências não sensíveis ────────────────────────────────────────────
  static Future<String> lerHost() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('servidor_host') ?? 'api.plegmadag.com';
  }

  static Future<void> salvarHost(String host) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('servidor_host', host);
  }

  static Future<bool> onboardingCompleto() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('onboarding_completo') ?? false;
  }

  static Future<void> marcarOnboardingCompleto() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_completo', true);
  }

  // ── Snapshot de Segurança (ZK-Integrity) ─────────────────────────────────
  static Future<void> salvarSnapshot(Map<String, dynamic> snapshot) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('security_snapshot', jsonEncode(snapshot));
  }

  static Future<Map<String, dynamic>?> lerSnapshot() async {
    final prefs = await SharedPreferences.getInstance();
    final raw   = prefs.getString('security_snapshot');
    if (raw == null) return null;
    try { return Map<String, dynamic>.from(jsonDecode(raw) as Map); }
    catch (_) { return null; }
  }

  static Future<bool> snapshotExiste() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.containsKey('security_snapshot');
  }

  static Future<void> salvarDeltaPendente(Map<String, dynamic> delta) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('snapshot_delta', jsonEncode(delta));
  }

  static Future<Map<String, dynamic>?> lerDeltaPendente() async {
    final prefs = await SharedPreferences.getInstance();
    final raw   = prefs.getString('snapshot_delta');
    if (raw == null) return null;
    try { return Map<String, dynamic>.from(jsonDecode(raw) as Map); }
    catch (_) { return null; }
  }

  static Future<void> limparDeltaPendente() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('snapshot_delta');
  }

  static Future<void> adiarSnapshot() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('snapshot_adiado', true);
  }

  static Future<bool> snapshotAdiado() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('snapshot_adiado') ?? false;
  }

  // ── Lattice Shield ────────────────────────────────────────────────────────
  static Future<void> shieldAtivoSalvar(bool ativo) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('shield_ativo', ativo);
  }

  static Future<bool> shieldAtivoLer() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('shield_ativo') ?? false;
  }

  // ── Validador 24h ─────────────────────────────────────────────────────────
  static Future<void> validadorAtivoSalvar(bool ativo) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('validador_ativo', ativo);
  }

  static Future<bool> validadorAtivoLer() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('validador_ativo') ?? false;
  }

  // ── Fila Offline ──────────────────────────────────────────────────────────
  static Future<void> adicionarFilaOffline(Map<String, dynamic> item) async {
    final prefs = await SharedPreferences.getInstance();
    final filaStr = prefs.getStringList('fila_offline') ?? [];
    item['offline_timestamp'] = DateTime.now().toIso8601String();
    filaStr.add(jsonEncode(item));
    await prefs.setStringList('fila_offline', filaStr);
  }

  static Future<List<Map<String, dynamic>>> lerFilaOffline() async {
    final prefs = await SharedPreferences.getInstance();
    final filaStr = prefs.getStringList('fila_offline') ?? [];
    return filaStr.map((e) => Map<String, dynamic>.from(jsonDecode(e))).toList();
  }

  static Future<void> limparFilaOffline() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('fila_offline');
  }

  // ── Sincronização dos dois backends ──────────────────────────────────────
  // Copia dados existentes de qualquer backend para o outro.
  // Garante que ambos ficam em paridade após qualquer evento de perda parcial.
  // Não apaga nada — apenas complementa o que está em falta.
  static Future<void> migrarStorageLegado() async {
    const keys = [
      'plg_private_key', 'plg_public_key', 'plg_address', 'plg_session_token',
      'plg_seed_phrase', 'plg_seed_backed', 'plg_seed_anchor_id',
    ];
    for (final k in keys) {
      try {
        String? vA, vB;
        try { vA = await _storageA.read(key: k); } catch (_) {}
        try { vB = await _storageB.read(key: k); } catch (_) {}

        // Copia A → B se B está vazio
        if (vA != null && vA.isNotEmpty && (vB == null || vB.isEmpty)) {
          try { await _storageB.write(key: k, value: vA); } catch (_) {}
        }
        // Copia B → A se A está vazio
        if (vB != null && vB.isNotEmpty && (vA == null || vA.isEmpty)) {
          try { await _storageA.write(key: k, value: vB); } catch (_) {}
        }

        // Espelha endereço em SharedPreferences
        final addr = vA ?? vB;
        if (k == 'plg_address' && addr != null && addr.startsWith('PLG')) {
          try {
            final prefs = await SharedPreferences.getInstance();
            await prefs.setString('plg_address_pub', addr);
          } catch (_) {}
        }
      } catch (_) {}
    }
  }

  // ── Limpa tudo (reset de fábrica) ─────────────────────────────────────────
  static Future<void> limparTudo() async {
    try { await _storageA.deleteAll(); } catch (_) {}
    try { await _storageB.deleteAll(); } catch (_) {}
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  }
}
