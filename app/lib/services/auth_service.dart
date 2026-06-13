import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'dilithium_ffi_service.dart';

// ============================================================================
// AUTH SERVICE — Autenticação dupla anti-coação
//
// B1 — Biometria do dispositivo (digital / face ID / PIN do sistema)
//   Idêntica ao desbloqueio do celular. Sob coação, o usuário usa apenas esta.
//   App permanece na tela neutra sem revelar que há uma segunda etapa.
//
// B2 — Padrão de pontos (segredo pessoal)
//   Configurado pelo usuário no primeiro boot.
//   Ativado por 3 toques no logo — sem nenhuma indicação visual.
//   Só após B2 o app é realmente desbloqueado.
// ============================================================================

class AuthService {
  static final _auth    = LocalAuthentication();
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _patternKey = 'plg_b2_pattern_hash';

  // ── Estado global de trava ─────────────────────────────────────────────────
  // Começa FALSE (desbloqueado). O boot chama lock() quando encontra
  // carteira existente — isso dispara o overlay via ValueListenableBuilder.
  static final ValueNotifier<bool> lockedNotifier = ValueNotifier(false);

  // ── Fase B1 concluída (persiste mesmo se widget for recriado) ─────────────
  static final ValueNotifier<bool> b1DoneNotifier = ValueNotifier(false);

  static bool get isLocked => lockedNotifier.value;

  // ── Grace period + gate de resumed (bloqueia paused tardio do MIUI) ────────
  //
  // MIUI abre o diálogo biométrico como Activity separada. Ao fechar, emite
  // AppLifecycleState.paused de forma atrasada — às vezes 3-5 s após o unlock
  // (fora do grace period simples). O gate _resumedAfterUnlock exige que o app
  // tenha recebido AppLifecycleState.resumed ANTES de aceitar qualquer novo
  // lock. O paused tardio do MIUI chega antes de resumed → gate = false → sem
  // loop. Apenas quando o usuário retorna ao app (resumed real) o gate abre e
  // a próxima ida ao background trava normalmente.
  static DateTime? _unlockTime;
  static const _kGraceMs = 2000;

  // True apenas após AppLifecycleState.resumed disparar pós-unlock.
  // Começa true (app inicia em resumed). lock() e unlock() resetam para false.
  static bool _resumedAfterUnlock = true;

  static bool get canLock {
    if (!_resumedAfterUnlock) return false;   // ainda não voltou ao foreground
    if (_unlockTime == null) return true;
    return DateTime.now().difference(_unlockTime!).inMilliseconds > _kGraceMs;
  }

  /// Chamado em AppLifecycleState.resumed — abre o gate para o próximo lock.
  static void markResumed() {
    _resumedAfterUnlock = true;
  }

  /// Impede que o observer do HomeScreen dispare lock durante autenticação
  /// externa (ex: auth QR no ShieldScreen). Chamar imediatamente antes de
  /// exibir qualquer diálogo biométrico fora do LockScreen.
  static void beginExternalAuth() {
    _resumedAfterUnlock = false;
  }

  static void lock() {
    _resumedAfterUnlock = false;
    b1DoneNotifier.value = false;
    if (!lockedNotifier.value) lockedNotifier.value = true;
  }

  static void unlock() {
    _resumedAfterUnlock = false; // aguarda resumed real antes de aceitar lock
    _unlockTime = DateTime.now();
    if (lockedNotifier.value) lockedNotifier.value = false;
  }

  static void markB1Done() {
    b1DoneNotifier.value = true;
  }

  // ── B1: Biometria do sistema (digital / face / PIN) ───────────────────────
  static Future<bool> authenticateBiometric({
    String reason = 'Desbloqueie o PLEGMA',
  }) async {
    if (kIsWeb) return true; // Web: biometria nativa indisponível — libera B1 automaticamente
    try {
      final supported = await _auth.isDeviceSupported();
      if (!supported) return true; // dispositivo sem biometria: libera
      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          biometricOnly: false, // permite fallback para PIN do sistema
          stickyAuth  : true,   // não cancela se o app perde foco brevemente
        ),
      );
    } catch (_) {
      return false;
    }
  }

  // ── B2: Padrão de pontos ───────────────────────────────────────────────────
  static Future<String> _hashPattern(String pattern) async {
    final bytes = Uint8List.fromList(utf8.encode('plegma_b2_salt_$pattern'));
    final hash  = await DilithiumFfiService.instance.blake3HashAsync(bytes);
    return DilithiumFfiService.bytesToHex(hash);
  }

  static Future<bool> isPatternSet() async {
    final v = await _storage.read(key: _patternKey);
    return v != null && v.isNotEmpty;
  }

  static Future<void> savePattern(String pattern) async =>
      _storage.write(key: _patternKey, value: await _hashPattern(pattern));

  static Future<bool> verifyPattern(String pattern) async {
    final stored = await _storage.read(key: _patternKey);
    if (stored == null) return false;
    return stored == await _hashPattern(pattern);
  }

  // Gap 1: permite resetar o padrão B2 após recuperação via seed phrase
  static Future<void> clearPattern() async =>
      _storage.delete(key: _patternKey);
}
