import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:battery_plus/battery_plus.dart';
import 'api_service.dart';
import 'dilithium_ffi_service.dart';

// =============================================================================
// VALIDATOR BACKGROUND SERVICE — PLEGMA DAG
//
// Foreground Service Android que mantém o heartbeat activo 24h enquanto
// o validador estiver ligado, independente de o app estar em foreground.
//
// Heartbeat: POST /api/node/heartbeat a cada 2 minutos.
// Suspensão automática:
//   - Bateria ≤ 10%
//   - Modo economia de bateria activo
// Retoma automaticamente quando as condições voltarem ao normal.
// =============================================================================

const _kIntervalMinutes  = 2;
const _kBatteryThreshold = 10;   // % mínimo para manter mineração
const _kNotifChannelId   = 'plegma_validator_channel'; // ignore: unused_element
const _kNotifId          = 888;

/// Inicializa o serviço (chamar uma vez no main(), antes de runApp).
Future<void> initValidatorBgService() async {
  if (kIsWeb) return;
  final svc = FlutterBackgroundService();
  await svc.configure(
    androidConfiguration: AndroidConfiguration(
      onStart                         : _onStart,
      autoStart                       : false, // Start explícito via botão para passar na checagem de Notificações do Android 13+
      isForegroundMode                : true,
      initialNotificationTitle        : 'PLEGMA · Validador Activo',
      initialNotificationContent      : 'Nó registado na rede DAG',
      foregroundServiceNotificationId : _kNotifId,
      foregroundServiceTypes          : [AndroidForegroundType.dataSync],
    ),
    iosConfiguration: IosConfiguration(
      autoStart    : false,
      onForeground : _onStart,
      onBackground : _onIosBackground,
    ),
  );
}

/// Inicia o foreground service (chamar quando o validador é ligado).
/// Garante configuração prévia — pode ser chamado sem ter chamado initValidatorBgService() antes.
Future<void> startValidatorBgService() async {
  if (kIsWeb) return;
  try {
    await initValidatorBgService();
    final svc = FlutterBackgroundService();
    await svc.startService();
    // Pede isenção de otimização de bateria para garantir execução com ecrã desligado
    if (!kIsWeb) {
      try {
        const _batteryChannel = MethodChannel('com.plegmadag.app/shield');
        await _batteryChannel.invokeMethod('requestIgnoreBatteryOptimizations');
      } catch (_) {
        // Silencioso — não bloquear o arranque do validador por falha de permissão
      }
    }
  } catch (_) {
    // Falha silenciosa — o HeartbeatService do isolate principal continua activo.
  }
}

/// Para o foreground service (chamar quando o validador é desligado).
Future<void> stopValidatorBgService() async {
  if (kIsWeb) return;
  final svc = FlutterBackgroundService();
  svc.invoke('stop');
}

/// Verifica se o serviço está a correr.
Future<bool> isValidatorBgServiceRunning() async {
  if (kIsWeb) return false;
  return FlutterBackgroundService().isRunning();
}

// ── Entrypoints do background isolate ────────────────────────────────────────

@pragma('vm:entry-point')
Future<bool> _onIosBackground(ServiceInstance service) async {
  return true;
}

@pragma('vm:entry-point')
void _onStart(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();

  final battery = Battery();
  bool _suspenso = false;

  // Parar quando invocado pelo app
  service.on('stop').listen((_) async {
    await service.stopSelf();
  });

  // Primeiro heartbeat imediato
  await _ciclo(service, battery, _suspenso);

  // Ciclo periódico a cada 2 minutos
  Timer.periodic(const Duration(minutes: _kIntervalMinutes), (_) async {
    if (!await FlutterBackgroundService().isRunning()) return;

    final nivel     = await battery.batteryLevel.catchError((_) => 100);
    final economiia = await battery.isInBatterySaveMode.catchError((_) => false);

    final deveSupender = nivel <= _kBatteryThreshold || economiia;

    if (deveSupender && !_suspenso) {
      // Acabou de entrar em suspensão
      _suspenso = true;
      final motivo = economiia
          ? 'Economia de bateria activa'
          : 'Bateria baixa (${nivel}%)';
      service.invoke('setNotificationInfo', {
        'title'  : 'PLEGMA · Validador em Pausa',
        'content': '$motivo · mineração suspensa',
      });
      return;
    }

    if (!deveSupender && _suspenso) {
      // Saiu da suspensão — retoma
      _suspenso = false;
    }

    if (!_suspenso) {
      await _ciclo(service, battery, _suspenso);
    }
  });
}

Future<void> _ciclo(
  ServiceInstance service,
  Battery battery,
  bool suspenso,
) async {
  try {
    // Para o serviço se o utilizador desativou manualmente enquanto o app estava fechado
    final prefs = await SharedPreferences.getInstance();
    if (!(prefs.getBool('validador_ativo') ?? false)) {
      await service.stopSelf();
      return;
    }

    final nivel     = await battery.batteryLevel.catchError((_) => 100);
    final economia  = await battery.isInBatterySaveMode.catchError((_) => false);

    if (nivel <= _kBatteryThreshold || economia) return;

    const storage = FlutterSecureStorage(
      aOptions: AndroidOptions(encryptedSharedPreferences: false),
    );
    final address = await storage.read(key: 'plg_address');
    if (address == null || address.isEmpty) return;

    final nodeId = 'VALIDATOR_$address';

    // Lê chaves do backend A (encryptedSharedPreferences: false — acessível no isolate bg)
    final privB64 = await storage.read(key: 'plg_private_key');
    final pubB64  = await storage.read(key: 'plg_public_key');

    String sigHex = '';
    String pubHex = '';

    if (privB64 != null && privB64.isNotEmpty && pubB64 != null && pubB64.isNotEmpty) {
      try {
        // DilithiumFfiService.instance carrega libdilithium_plegma.so via FFI
        // A biblioteca nativa é partilhada no processo — acessível no background isolate
        final svc    = DilithiumFfiService.instance;
        final msgBytes = Uint8List.fromList(utf8.encode(nodeId));
        final privKey  = base64.decode(privB64);
        final sig      = svc.sign(msgBytes, privKey);
        sigHex = DilithiumFfiService.bytesToHex(sig);
        pubHex = DilithiumFfiService.bytesToHex(base64.decode(pubB64));
      } catch (_) {
        // FFI falhou no isolate bg — envia sem assinatura (fallback)
      }
    }

    final result = await ApiService.nodeHeartbeat(
      nodeId,
      publicKey : pubHex,
      signature : sigHex,
      metadata  : {
        'node_type'  : 'VALIDATOR',
        'plg_address': address,
        'battery_pct': nivel,
      },
    );

    final ok = result?['ok'] == true;
    
    if (ok) {
      // ── MODO ONLINE ──
      service.invoke('setNotificationInfo', {
        'title'  : 'PLEGMA · Validador Activo',
        'content': 'Último ping: ${_horaActual()} · bateria ${nivel}%',
      });
      
      // Sincroniza transferências e pings guardados
      final prefs = await SharedPreferences.getInstance();
      final filaStr = prefs.getStringList('fila_offline') ?? [];
      if (filaStr.isNotEmpty) {
        // Envia log de sincronização retroativa
        await ApiService.nodeHeartbeat(
          nodeId, publicKey: pubHex, signature: sigHex,
          metadata: {'offline_sync_count': filaStr.length, 'plg_address': address}
        );
        await prefs.remove('fila_offline');
      }
    } else {
      // ── MODO OFFLINE ──
      service.invoke('setNotificationInfo', {
        'title'  : 'PLEGMA · Validador (Modo Offline)',
        'content': 'Armazenando blocos localmente...',
      });
      
      // Guarda batimento cardíaco na fila
      final prefs = await SharedPreferences.getInstance();
      final filaStr = prefs.getStringList('fila_offline') ?? [];
      final offlineItem = {
        'type': 'heartbeat',
        'address': address,
        'timestamp': DateTime.now().toIso8601String()
      };
      filaStr.add(jsonEncode(offlineItem));
      await prefs.setStringList('fila_offline', filaStr);
    }
  } catch (_) {
    // Silencioso — salva offline emergencial se houver falha dura de rede
    final prefs = await SharedPreferences.getInstance();
    final filaStr = prefs.getStringList('fila_offline') ?? [];
    filaStr.add(jsonEncode({'type': 'heartbeat_emergency', 'timestamp': DateTime.now().toIso8601String()}));
    await prefs.setStringList('fila_offline', filaStr);
  }
}

String _horaActual() {
  final now = DateTime.now();
  return '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
}
