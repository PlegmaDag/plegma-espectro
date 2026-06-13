import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import '../models/wallet_model.dart';
import '../services/api_service.dart';
import '../services/dilithium_ffi_service.dart';
import '../services/storage_service.dart';

class WalletProvider extends ChangeNotifier {
  WalletModel? _wallet;
  List<VestingContrato> _vestings = [];
  List<TransacaoHistorico> _extrato = [];
  List<ProverVinculado> _provers = [];
  int _countProvers     = 0;
  int _countValidadores = 0;
  OfertaP2P? _ofertaRecebida;
  List<double> _precoHistorico = [];
  // PLG-G: preço definido exclusivamente pelo Sócio vendedor (sem simulação)
  double  _plggPreco           = 0.10;   // base Genesis até primeira venda P2P
  String  _plggFonte           = 'genesis'; // 'genesis' ou 'p2p'
  String? _plggUltimaVendaData;           // data da última venda P2P
  int     _plggNumVendas       = 0;

  bool _carregando = false;
  bool _transacoesAtivas = false;
  double? _precoPlgReal;
  String? _erro;
  Timer? _timer;
  Timer? _timerPreco;
  Timer? _timerSim;

  // Contador para simulação determinística via BLAKE3
  int _simCounter = 0;

  // Gera double [0,1) determinístico para simulação visual de preço
  double _nextSimDouble() {
    _simCounter++;
    try {
      final input = Uint8List.fromList(utf8.encode('PLG_PRECO_SIM:$_simCounter'));
      final hash  = DilithiumFfiService.instance.blake3Hash(input);
      return ((hash[0] << 8) | hash[1]) / 65535.0;
    } catch (_) {
      // Fallback determinístico quando FFI indisponível (apenas para gráfico)
      int x = _simCounter * 2654435761;
      x = ((x ^ (x >> 16)) * 0x45d9f3b) & 0xFFFFFFFF;
      return (x & 0xFFFF) / 65535.0;
    }
  }

  // ── Getters ───────────────────────────────────────────────────────────────
  WalletModel?              get wallet    => _wallet;
  List<VestingContrato>     get vestings  => _vestings;
  List<TransacaoHistorico>  get extrato   => _extrato;
  List<ProverVinculado>     get provers          => _provers;
  int                       get countProvers      => _countProvers;
  int                       get countValidadores  => _countValidadores;
  OfertaP2P?                get ofertaRecebida    => _ofertaRecebida;
  List<double>              get precoHistorico     => _precoHistorico;
  bool                      get carregando => _carregando;
  String?                   get erro      => _erro;
  bool                      get temCarteira => _wallet != null;
  bool                      get transacoesAtivas => _transacoesAtivas;

  double  get plgPreco          => _wallet?.plgPreco ?? 0.0047;
  double  get plgVariacao       => _wallet?.plgVariacao ?? 0;
  double  get plggPreco         => _plggPreco;
  String  get plggFonte         => _plggFonte;           // 'genesis' ou 'p2p'
  String? get plggUltimaVendaData => _plggUltimaVendaData;
  int     get plggNumVendas     => _plggNumVendas;
  bool    get plggSemVendas     => _plggNumVendas == 0;  // true enquanto mercado P2P inativo

  // ── Inicialização ─────────────────────────────────────────────────────────
  Future<void> inicializar() async {
    final host = await StorageService.lerHost();
    ApiService.setHost(host);

    _iniciarSimulacaoPlg();
    // Paralelo — elimina 3× timeout em série (máx 8s em vez de 24s offline)
    await Future.wait([
      fetchStatus(),
      _fetchUltimoPrecoPlgg(),
      _fetchRedeFase(),
    ]);

    // Polling a cada 5 segundos
    _timer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => fetchStatus(),
    );
    // Preço PLG-G + extrato: recarrega a cada 10 segundos
    _timerPreco = Timer.periodic(
      const Duration(seconds: 10),
      (_) async {
        await _fetchUltimoPrecoPlgg();
        await _fetchRedeFase();
        await fetchExtrato();
      },
    );
  }

  void _iniciarSimulacaoPlg() {
    // PLG: popula histórico inicial a partir de $0.0047 (simulação local apenas para PLG)
    double preco = 0.0047;
    for (int i = 0; i < 60; i++) {
      preco *= (1 + (_nextSimDouble() - 0.495) * 0.018);
      preco = preco.clamp(0.0001, 1.0);
      _precoHistorico.add(preco);
    }
    // Tick PLG a cada 2.5 segundos — referência salva para cancelar no dispose
    _timerSim = Timer.periodic(
      const Duration(milliseconds: 2500),
      (_) => _tickPrecoPlg(),
    );
  }

  void _tickPrecoPlg() {
    // Quando pool ativa, usa preço real em vez de simulação
    if (_transacoesAtivas && _precoPlgReal != null) return;
    double preco = _precoHistorico.last;
    preco *= (1 + (_nextSimDouble() - 0.492) * 0.018);
    preco = preco.clamp(0.0001, 1.0);
    _precoHistorico.add(preco);
    if (_precoHistorico.length > 60) _precoHistorico.removeAt(0);
    final variacao = ((_precoHistorico.last - _precoHistorico.first) / _precoHistorico.first) * 100;
    if (_wallet != null) {
      _wallet = _wallet!.copyWith(plgPreco: preco, plgVariacao: variacao);
    }
    notifyListeners();
  }

  /// Busca o último preço PLG-G do servidor — determinado exclusivamente pelo Sócio vendedor.
  Future<void> _fetchUltimoPrecoPlgg() async {
    final data = await ApiService.getUltimoPrecoPlgg();
    if (data != null) {
      _plggPreco          = (data['preco'] ?? 0.10).toDouble();
      _plggFonte          = data['fonte'] ?? 'genesis';
      _plggUltimaVendaData = data['ultima_venda_data'] as String?;
      _plggNumVendas      = (data['num_vendas_p2p'] ?? 0) as int;
      notifyListeners();
    }
  }

  /// Verifica fase da rede e busca preço real do PLG quando pool ativa.
  Future<void> _fetchRedeFase() async {
    final data = await ApiService.getRedeFase();
    if (data == null) return;
    _transacoesAtivas = data['transacoes_ativas'] == true;

    if (_transacoesAtivas) {
      // Pool ativa — busca preço real (P = L / S)
      final cotacao = await ApiService.getPoolCotacao();
      if (cotacao != null) {
        final precoInicial = (cotacao['preco_inicial'] as num?)?.toDouble();
        if (precoInicial != null && precoInicial > 0) {
          _precoPlgReal = precoInicial;
          if (_wallet != null) {
            _wallet = _wallet!.copyWith(plgPreco: _precoPlgReal!);
          }
          notifyListeners();
        }
      }
    }
  }

  // ── Fetch principal ───────────────────────────────────────────────────────
  Future<void> fetchStatus() async {
    final preco    = _wallet?.plgPreco    ?? 0.0047;
    final variacao = _wallet?.plgVariacao ?? 0;

    // Recupera endereço PLG salvo localmente (com retry embutido no StorageService)
    String plgAddress = await StorageService.lerEndereco() ?? '';
    // Se ainda vazio na primeira chamada após boot, aguarda e tenta de novo
    if (plgAddress.isEmpty && _wallet == null) {
      await Future.delayed(const Duration(milliseconds: 600));
      plgAddress = await StorageService.lerEndereco() ?? '';
    }

    // 1) Status DAG (/api/status) — usado como base do wallet
    final data = await ApiService.dagStatus();
    if (data != null) {
      // Monta wallet a partir dos dados DAG disponíveis.
      // O core não retorna campos de saldo PLG individuais neste endpoint;
      // eles virão de getGenesisSaldo abaixo.
      _wallet = WalletModel(
        plgAddress        : plgAddress,
        disponivel        : (_wallet?.disponivel        ?? 0),
        vestingLocked     : (_wallet?.vestingLocked     ?? 0),
        totalEstimado     : (_wallet?.totalEstimado     ?? 0),
        mineradoTotal     : (_wallet?.mineradoTotal     ?? 0),
        enviadoTotal      : (_wallet?.enviadoTotal      ?? 0),
        recebidoTotal     : (_wallet?.recebidoTotal     ?? 0),
        vestingValidator  : (_wallet?.vestingValidator  ?? 0),
        vestingProver     : (_wallet?.vestingProver     ?? 0),
        proversVinculados : (_wallet?.proversVinculados ?? 0),
        proximaLiberacao  : _wallet?.proximaLiberacao,
        plgPreco          : preco,
        plgVariacao       : variacao,
        // Mantém PLG-G existente até ser atualizado abaixo
        plggTotal         : _wallet?.plggTotal       ?? 0,
        plggLocked        : _wallet?.plggLocked      ?? 0,
        plggAvailable     : _wallet?.plggAvailable   ?? 0,
        plggUnlockDate    : _wallet?.plggUnlockDate,
        categoria         : _wallet?.categoria       ?? 'APOIADOR',
        boostMineracao    : _wallet?.boostMineracao  ?? 1.0,
      );
      _erro = null;
    } else {
      _erro = 'Servidor offline';
      // Offline: cria estrutura vazia com endereço real — sem dados fictícios
      if (_wallet == null) _wallet = _walletDemo(plgAddress);
    }

    // 2) Saldo PLG real (/api/wallet/status) — sobrescreve os valores preservados
    if (plgAddress.isNotEmpty) await _fetchWalletSaldo(plgAddress);

    // 3) Prioridade Genesis (/api/priority) — categoria e boost
    if (plgAddress.isNotEmpty) {
      await _fetchPriority(plgAddress);
      // 4) Saldo PLG-G (/api/genesis/saldo)
      await _fetchGenesisSaldo(plgAddress);
      // 5) Provers/Validadores vinculados — contagens para o dashboard
      await fetchProvers();
      // 6) Oferta P2P pendente recebida
      await _fetchOfertaPendente(plgAddress);
    }

    notifyListeners();
  }

  /// Busca saldo PLG mainnet por endereço via /api/wallet/status
  /// PLG tem lockup 30 dias (Aerarium): saldo_plg_liberado = 0 até dia 31.
  Future<void> _fetchWalletSaldo(String plgAddress) async {
    final data = await ApiService.getWalletStatus(plgAddress);
    if (data != null && _wallet != null) {
      final totalPlg    = (data['saldo_plg']          ?? 0).toDouble();
      final liberadoPlg = (data['saldo_plg_liberado']  ?? 0).toDouble();
      final lockedPlg   = (data['saldo_plg_locked']    ?? 0).toDouble();
      _wallet = _wallet!.copyWith(
        disponivel    : liberadoPlg,   // PLG disponível (lockup 30d expirado)
        vestingLocked : lockedPlg,     // PLG em lockup (minerado < 30 dias)
        totalEstimado : totalPlg,      // PLG total minerado
      );
    }
  }

  /// Atualiza categoria, boost e Selo Sócio Genesis via /api/priority
  Future<void> _fetchPriority(String plgAddress) async {
    final data = await ApiService.getPriority(plgAddress);
    if (data != null && _wallet != null) {
      final categoria             = data['categoria']               as String? ?? 'APOIADOR';
      final boost                 = (data['boost']                  ?? 1.0).toDouble();
      final pesoVoto              = (data['peso_voto']              ?? 1.0).toDouble();
      final socioGenesis          = data['socio_genesis']           as bool? ?? false;
      final seloAtivo             = data['selo_genesis_ativo']      as bool? ?? false;
      final statusPerdido         = data['status_genesis_perdido']  as bool? ?? false;
      _wallet = _wallet!.copyWith(
        categoria            : categoria,
        boostMineracao       : boost,
        pesoVoto             : pesoVoto,
        socioGenesis         : socioGenesis,
        seloGenesisAtivo     : seloAtivo,
        statusGenesisPerdido : statusPerdido,
      );
    }
    // Se offline: mantém valores existentes (default APOIADOR / 1.0)
  }

  /// Atualiza saldo PLG-G via /api/genesis/saldo
  /// Contrato canônico: saldo_total, saldo_liberado, saldo_bloqueado, proximo_unlock
  Future<void> _fetchGenesisSaldo(String plgAddress) async {
    final data = await ApiService.getGenesisSaldo(plgAddress);
    if (data != null && _wallet != null) {
      final total      = (data['saldo_total']     ?? 0).toDouble();
      final locked     = (data['saldo_bloqueado'] ?? 0).toDouble();
      final available  = (data['saldo_liberado']  ?? 0).toDouble();
      final unlockDate = data['proximo_unlock']   as String?;
      _wallet = _wallet!.copyWith(
        plggTotal      : total,
        plggLocked     : locked,
        plggAvailable  : available,
        plggUnlockDate : unlockDate,
      );
    }
    // Se offline: mantém plgg = 0 (modo seguro)
  }

  // ── Vesting / Extrato / Provers ───────────────────────────────────────────
  Future<void> fetchVesting() async {
    final data = await ApiService.walletVesting();
    if (data != null) {
      final locked = (data['locked'] as List? ?? []);
      _vestings = locked.map((j) => VestingContrato.fromJson(j)).toList();
      notifyListeners();
    }
  }

  Future<void> fetchExtrato({String? filtro}) async {
    // Usa sempre o endereço guardado no storage como fonte de verdade,
    // evitando que o endereço demo 'PLG000...' consulte o servidor.
    final address = await StorageService.lerEndereco() ?? _wallet?.plgAddress ?? '';
    if (address.isEmpty || address == 'PLG0000000000000000000000000000000000000000') return;
    final list = await ApiService.getWalletExtrato(address);
    if (list != null) {
      _extrato = list.map((j) {
        final m        = j as Map<String, dynamic>;
        final nodeType = (m['node_type'] ?? '').toString().toUpperCase();
        final de       = m['de']   ?? m['remetente']   ?? '';
        final para     = m['para'] ?? m['destinatario'] ?? '';
        final isSaida  = de == address;

        // Determina o tipo com base em node_type (prioridade) ou direcção
        final String tipo;
        if (nodeType == 'GENESIS') {
          tipo = 'PLG-G';
        } else if (nodeType == 'VALIDATOR' || nodeType == 'PROVER') {
          tipo = 'MINERADO';
        } else if (nodeType == 'VESTING_LIBERADO') {
          tipo = 'VESTING_LIBERADO';
        } else {
          tipo = isSaida ? 'ENVIADO' : 'RECEBIDO';
        }

        final contraparte = (nodeType == 'GENESIS')
            ? 'GENESIS'
            : (isSaida ? para : de);

        // Converte timestamp (epoch float) para data legível
        String dataStr = '';
        final tsRaw = m['timestamp'] ?? m['data'];
        if (tsRaw != null) {
          if (tsRaw is num) {
            final dt = DateTime.fromMillisecondsSinceEpoch(
                (tsRaw * 1000).toInt(), isUtc: false);
            dataStr = '${dt.day.toString().padLeft(2,'0')}/'
                     '${dt.month.toString().padLeft(2,'0')}/'
                     '${dt.year} '
                     '${dt.hour.toString().padLeft(2,'0')}:'
                     '${dt.minute.toString().padLeft(2,'0')}';
          } else {
            dataStr = tsRaw.toString();
          }
        }

        return TransacaoHistorico(
          txId        : m['hash']         ?? m['tx_hash'] ?? '',
          tipo        : tipo,
          amount      : (m['amount']      ?? m['valor'] ?? 0).toDouble(),
          contraparte : contraparte,
          data        : dataStr,
          status      : m['status']       ?? 'confirmada',
          fonte       : m['fonte']        ?? '',
          releaseDate : m['release_date']?.toString() ?? '',
        );
      }).toList();
      notifyListeners();
    }
  }

  Future<void> fetchProvers() async {
    // Usa storage como fonte primária — evita race condition com _wallet null
    final address = await StorageService.lerEndereco()
        ?? _wallet?.plgAddress
        ?? '';
    if (address.isEmpty ||
        address == 'PLG0000000000000000000000000000000000000000') {
      _provers          = [];
      _countProvers     = 0;
      _countValidadores = 0;
      notifyListeners();
      return;
    }
    final data = await ApiService.walletProvers(address: address);
    if (data != null) {
      final list = (data['provers'] as List? ?? []);
      _provers          = list.map((j) => ProverVinculado.fromJson(j)).toList();
      _countProvers     = (data['count_provers']     as int?) ?? _provers.length;
      _countValidadores = (data['count_validadores'] as int?) ?? 0;
      notifyListeners();
    }
  }

  Future<void> _fetchOfertaPendente(String address) async {
    final data = await ApiService.getOfertaPendente(address);
    if (data != null && data['oferta_id'] != null) {
      _ofertaRecebida = OfertaP2P.fromJson(data);
    } else {
      _ofertaRecebida = null;
    }
  }

  /// Cria oferta de venda P2P de PLG-G para um comprador específico.
  Future<Map<String, dynamic>?> criarOfertaPlgg({
    required String comprador,
    required double amountPlgg,
    required double precoUnitario,
  }) async {
    final vendedor = _wallet?.plgAddress ?? '';
    if (vendedor.isEmpty) return null;
    return ApiService.criarOfertaPlgg(
      vendedor      : vendedor,
      comprador     : comprador,
      amountPlgg    : amountPlgg,
      precoUnitario : precoUnitario,
    );
  }

  /// Comprador aceita ou rejeita oferta recebida.
  Future<Map<String, dynamic>?> responderOferta({
    required String ofertaId,
    required bool   aceitar,
  }) async {
    final comprador = _wallet?.plgAddress ?? '';
    if (comprador.isEmpty) return null;
    final result = await ApiService.responderOferta(
      ofertaId : ofertaId,
      comprador: comprador,
      aceitar  : aceitar,
    );
    if (result?['ok'] == true) {
      _ofertaRecebida = null;
      notifyListeners();
    }
    return result;
  }

  Future<bool> vincularProver({
    required String nodeId,
    required String categoria,
    required int    score,
  }) async {
    final address = _wallet?.plgAddress ?? await StorageService.lerEndereco() ?? '';
    if (address.isEmpty) return false;
    final result = await ApiService.post(
      '${ApiService.poolBaseUrl}/wallet/vincular_prover',
      {'node_id': nodeId, 'categoria': categoria, 'score': score, 'plg_address': address},
    );
    return result?['ok'] == true;
  }

  Future<bool> desvincularProver(String nodeId) async {
    final address = _wallet?.plgAddress ?? await StorageService.lerEndereco() ?? '';
    if (address.isEmpty) return false;
    final result = await ApiService.desvincularProver(
      nodeId     : nodeId,
      plgAddress : address,
    );
    if (result?['ok'] == true) {
      _provers = _provers.where((p) => p.nodeId != nodeId).toList();
      notifyListeners();
      return true;
    }
    return false;
  }

  Future<Map<String, dynamic>?> transferir({
    required String destinatario,
    required double amount,
  }) {
    // Rejeita amounts não-finitos (SERIAL-01 fix)
    if (!amount.isFinite || amount <= 0) return Future.value(null);
    final de = _wallet?.plgAddress ?? '';
    if (de.isEmpty) return Future.value(null);
    // Proíbe auto-transferência no cliente
    if (destinatario == de) {
      return Future.value({'erro': 'auto-transferencia proibida'});
    }
    return ApiService.walletTransferir(
      de          : de,
      destinatario: destinatario,
      amount      : amount,
    );
  }

  /// Transfere PLG-G (token de governança) — endpoint dedicado
  Future<Map<String, dynamic>?> transferirPlgg({
    required String destinatario,
    required double amount,
  }) {
    if (!amount.isFinite || amount <= 0) return Future.value(null);
    final de = _wallet?.plgAddress ?? '';
    if (de.isEmpty) return Future.value(null);
    // Proíbe auto-transferência no cliente
    if (destinatario == de) {
      return Future.value({'erro': 'auto-transferencia proibida'});
    }
    return ApiService.walletTransferir(
      de          : de,
      destinatario: destinatario,
      amount      : amount,
      token       : 'PLG-G',
    );
  }

  // ── Estrutura vazia (offline) — sem valores fictícios ─────────────────────
  WalletModel _walletDemo(String addr) => WalletModel(
    plgAddress       : addr.isNotEmpty ? addr : 'PLG0000000000000000000000000000000000000000',
    disponivel       : 0,
    vestingLocked    : 0,
    totalEstimado    : 0,
    mineradoTotal    : 0,
    enviadoTotal     : 0,
    recebidoTotal    : 0,
    vestingValidator : 0,
    vestingProver    : 0,
    proversVinculados: 0,
    proximaLiberacao : null,
    plgPreco         : 0.0047,
    plgVariacao      : 0,
    plggTotal        : 0,
    plggLocked       : 0,
    plggAvailable    : 0,
    categoria        : 'APOIADOR',
    boostMineracao   : 1.0,
    pesoVoto         : 1.0,
  );

  @override
  void dispose() {
    _timer?.cancel();
    _timerPreco?.cancel();
    _timerSim?.cancel();
    super.dispose();
  }
}
