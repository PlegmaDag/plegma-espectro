import 'dart:async';
import 'package:flutter/foundation.dart';
import '../services/api_service.dart';
import '../services/storage_service.dart';
import '../services/validator_bg_service.dart';

class ValidatorProvider extends ChangeNotifier {
  bool      _minerando          = false;
  bool      _dagOnline          = false;
  int       _nosAtivos          = 0;
  int       _nosAncoras         = 0;
  int       _nosMineradores     = 0;
  int       _validadoresAtivos  = 0;
  double    _hashrate           = 0;
  double    _recompensa         = 0;
  int       _aceitas            = 0;
  String    _uptime             = '00:00:00';
  String    _lastHash           = '--';
  String    _nodeType           = 'VALIDATOR';
  String    _address            = '';
  DateTime? _miningStart;       // instante em que _minerando ficou true
  Timer?    _timer;

  bool   get minerando         => _minerando;
  bool   get dagOnline         => _dagOnline;
  int    get nosAtivos         => _nosAtivos;
  int    get nosAncoras        => _nosAncoras;
  int    get nosMineradores    => _nosMineradores;
  int    get validadoresAtivos => _validadoresAtivos;
  double get hashrate          => _hashrate;
  double get recompensa        => _recompensa;
  int    get aceitas           => _aceitas;
  String get uptime            => _uptime;
  String get lastHash          => _lastHash;
  String get nodeType          => _nodeType;

  Future<void> inicializar() async {
    _address = await StorageService.lerEndereco() ?? '';
    // Retry se Keystore ainda não disponível logo após boot
    if (_address.isEmpty) {
      await Future.delayed(const Duration(milliseconds: 800));
      _address = await StorageService.lerEndereco() ?? '';
    }
    _minerando = await StorageService.validadorAtivoLer();
    if (_minerando) {
      _miningStart = DateTime.now();
      try {
        final running = await isValidatorBgServiceRunning();
        if (!running) await startValidatorBgService();
      } catch (_) {
        // Bg service não suportado nesta plataforma — continua sem ele.
      }
    }
    await _fetch();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) => _fetch());
  }

  Future<void> _fetch() async {
    // DAG status
    final dag = await ApiService.dagStatus();
    if (dag != null) {
      _dagOnline         = true;
      _nosAtivos         = (dag['nos_ativos']         ?? 0) as int;
      _nosAncoras        = (dag['nos_ancoras']        ?? 0) as int;
      _nosMineradores    = (dag['nos_mineradores']    ?? 0) as int;
      _validadoresAtivos = (dag['validadores_ativos'] ?? 0) as int;
      // Hashrate da rede (todos os miners+validadores activos)
      _hashrate          = ((dag['hashrate_rede']     ?? 0) as num).toDouble();
    } else {
      _dagOnline = false;
    }

    // Miner stats — apenas métricas de exibição; estado activo é controlado localmente
    if (_address.isNotEmpty) {
      final miner = await ApiService.minerStatus(address: _address);
      if (miner != null) {
        _recompensa = 0;
        _aceitas    = (miner['blocos_aceitos']     ?? 0) as int;
        _nodeType   = 'VALIDATOR';
      }
    }

    // Uptime incremental (calculado localmente enquanto minerando)
    if (_minerando && _miningStart != null) {
      final diff = DateTime.now().difference(_miningStart!);
      final h = diff.inHours.toString().padLeft(2, '0');
      final m = (diff.inMinutes % 60).toString().padLeft(2, '0');
      final s = (diff.inSeconds % 60).toString().padLeft(2, '0');
      _uptime = '$h:$m:$s';
    }

    // Last block
    final block = await ApiService.dagLastBlock();
    if (block != null) {
      final hash = block['last_vertex_hash'] ?? '';
      _lastHash = hash.isNotEmpty
          ? '${hash.substring(0, 12)}...${hash.substring(hash.length - 8)}'
          : '--';
    }

    notifyListeners();
  }

  Future<bool> toggleMineracao() async {
    if (_address.isEmpty) return false;
    final novoEstado = !_minerando;
    await StorageService.validadorAtivoSalvar(novoEstado);
    if (novoEstado) {
      _miningStart = DateTime.now();
      _uptime = '00:00:00';
      await startValidatorBgService();
    } else {
      _miningStart = null;
      _uptime = '00:00:00';
      await stopValidatorBgService();
    }
    _minerando = novoEstado;
    notifyListeners();
    return true;
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
