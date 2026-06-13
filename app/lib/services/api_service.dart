import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dilithium_ffi_service.dart';

// ============================================================================
// API SERVICE — Comunicação com o Core PLEGMA
//
// Endpoints públicos servidos em https://plegmadag.com:
//
//   GET  /api/status                   — estado da rede DAG
//   GET  /api/lastBlock                — último vértice do DAG
//   POST /api/mine                     — submissão de vértice
//   GET  /api/priority?address=PLG_..  — categoria e boost do sócio Genesis
//   GET  /api/genesis/status           — status geral da venda Genesis
//   GET  /api/genesis/saldo?address=.. — saldo PLG-G de um endereço
//   POST /api/genesis/registrar        — registrar intenção de compra
//   POST /api/genesis/transferir       — transferência P2P PLG-G
//   POST /api/genesis/configurar       — configurar monitor (admin)
//   GET  /api/peer/hashes              — hashes que este nó possui (gossip)
//   GET  /api/peer/vertex/:hash        — vértice específico por hash (gossip)
//   POST /api/peer/vertex              — receber vértice propagado (gossip)
// ============================================================================

class ApiService {
  static const String defaultHost = 'api.plegmadag.com';
  static String _host = defaultHost;
  static const int _timeout = 8;

  static String get baseUrl => _host.contains('.') && !_isIp(_host)
      ? 'https://$_host'
      : 'http://$_host:8080';

  static bool _isIp(String h) =>
      RegExp(r'^\d{1,3}(\.\d{1,3}){3}$').hasMatch(h);

  static void setHost(String host) {
    final clean = host.trim();
    // Aceita apenas hostname RFC-3986 ou IPv4: letras, dígitos, ponto, hífen.
    // Rejeita CRLF, espaços, barras e qualquer outro char que permita
    // header injection, request smuggling ou URL hijacking.
    final isValidHostname = RegExp(
      r'^[a-zA-Z0-9]([a-zA-Z0-9\-.]*[a-zA-Z0-9])?$',
    ).hasMatch(clean);
    final isIPv6 = clean.startsWith('[') && clean.endsWith(']');
    if (isValidHostname || isIPv6) {
      _host = clean;
    }
    // Entrada inválida: mantém o host anterior sem alteração.
  }

  static final _client = http.Client();

  // ── DAG ───────────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>?> dagStatus() =>
      _get('/api/status');

  static Future<Map<String, dynamic>?> dagLastBlock() =>
      _get('/api/lastBlock');

  static Future<Map<String, dynamic>?> dagMine(Map<String, dynamic> body) =>
      _post('/api/mine', body);

  // ── Genesis ───────────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>?> getGenesisStatus() =>
      _get('/api/genesis/status');

  static Future<Map<String, dynamic>?> getGenesisSaldo(String plgAddress) =>
      _get('/api/genesis/saldo?address=$plgAddress');

  static Future<Map<String, dynamic>?> registrarIntencao(
      String plgAddress, double usdtAmount) =>
      _post('/api/genesis/registrar', {
        'plg_address': plgAddress,
        'usdt_amount': usdtAmount,
      });

  static Future<Map<String, dynamic>?> transferirPlgg({
    required String de,
    required String para,
    required double amount,
    bool confirmado = false,
    double? precoUnitario,   // preço em USDC definido pelo Sócio vendedor
  }) =>
      _post('/api/genesis/transferir', {
        'de'             : de,
        'para'           : para,
        'amount'         : amount,
        'confirmado'     : confirmado,
        if (precoUnitario != null) 'preco_unitario': precoUnitario,
      });

  /// Último preço PLG-G registrado (definido pelo Sócio vendedor)
  static Future<Map<String, dynamic>?> getUltimoPrecoPlgg() =>
      _get('/api/genesis/ultimo_preco');

  // ── Priority / Categoria ──────────────────────────────────────────────────
  static Future<Map<String, dynamic>?> getPriority(String plgAddress) =>
      _get('/api/priority?address=$plgAddress');

  // ── Gossip / Peer ─────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>?> peerHashes() =>
      _get('/api/peer/hashes');

  static Future<Map<String, dynamic>?> peerVertex(String hash) =>
      _get('/api/peer/vertex/$hash');

  static Future<Map<String, dynamic>?> peerEnviarVertex(
      Map<String, dynamic> body) =>
      _post('/api/peer/vertex', body);

  // ── Compatibilidade com providers existentes ──────────────────────────────
  // Esses métodos mapeiam para os endpoints reais do core_vm.py.
  // Não existe mais walletUrl separado — tudo usa baseUrl (:8080).

  /// Status da carteira: usa /api/status (retorna dados DAG + rede).
  /// Dados de saldo específicos vêm de getGenesisSaldo().
  static Future<Map<String, dynamic>?> walletStatus() =>
      _get('/api/status');

  /// Não existe endpoint de vesting no core atual — retorna null offline.
  static Future<Map<String, dynamic>?> walletVesting() async => null;

  /// Não existe endpoint de extrato no core atual — retorna null offline.
  static Future<Map<String, dynamic>?> walletExtrato({String? filtro}) async => null;

  /// Provers vinculados à carteira: GET /wallet/provers?address=<address>
  static Future<Map<String, dynamic>?> walletProvers({String address = ''}) =>
      get('$_poolBase/wallet/provers${address.isNotEmpty ? '?address=$address' : ''}');

  /// Desvincula um Prover: POST /wallet/desvincular_prover
  static Future<Map<String, dynamic>?> desvincularProver({
    required String nodeId,
    required String plgAddress,
  }) =>
      post('$_poolBase/wallet/desvincular_prover', {
        'node_id'    : nodeId,
        'plg_address': plgAddress,
      });

  /// Transferência de tokens via /api/genesis/transferir (PLG ou PLG-G).
  ///
  /// Segurança:
  ///   - [de] obrigatório: enviado explicitamente (nunca string vazia).
  ///   - [token] whitelisted: apenas 'PLG' ou 'PLG-G'.
  ///   - [nonce] BLAKE3(timestamp_µs + de): proteção anti-replay no servidor.
  static Future<Map<String, dynamic>?> walletTransferir({
    required String de,
    required String destinatario,
    required double amount,
    String token = 'PLG',
  }) async {
    // Whitelist de token — rejeita qualquer valor fora do protocolo (Lei HTML/injection)
    if (token != 'PLG' && token != 'PLG-G') return null;
    // Nonce anti-replay: BLAKE3(timestamp_µs_hex + de) — determinístico, pós-quântico.
    final ts    = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
    final input = Uint8List.fromList(utf8.encode('$ts$de'));
    final hash  = await DilithiumFfiService.instance.blake3HashAsync(input);
    final nonce = DilithiumFfiService.bytesToHex(hash);
    return _post('/api/genesis/transferir', {
      'de'    : de,
      'para'  : destinatario,
      'amount': amount,
      'token' : token,
      'nonce' : nonce,
    });
  }

  /// Miner status por address: GET /api/miner/status?address=
  static Future<Map<String, dynamic>?> minerStatus({String address = ''}) =>
      _get('/api/miner/status?address=${Uri.encodeComponent(address)}');

  /// Pausa o minerador: POST /api/miner/pause
  static Future<Map<String, dynamic>?> minerPause(String address) =>
      _post('/api/miner/pause', {'address': address});

  /// Resume o minerador: POST /api/miner/resume
  static Future<Map<String, dynamic>?> minerResume(String address) =>
      _post('/api/miner/resume', {'address': address});

  // ── Wallet (novos endpoints) ──────────────────────────────────────────────
  /// Status da carteira por endereço: GET /api/wallet/status?address=
  static Future<Map<String, dynamic>?> getWalletStatus(String address) =>
      _get('/api/wallet/status?address=$address');

  /// Extrato de transações por endereço: GET /api/wallet/extrato?address=
  static Future<List<dynamic>?> getWalletExtrato(String address) async {
    final data = await _get('/api/wallet/extrato?address=$address');
    if (data == null) return null;
    final list = data['transacoes'] ?? data['extrato'] ?? data['transactions'] ?? data['txs'];
    if (list is List) return list;
    return null;
  }

  /// Transferência PLG: POST /api/wallet/transferir
  static Future<Map<String, dynamic>?> transferirPlg({
    required String de,
    required String para,
    required double amount,
    required String assinatura,
  }) =>
      _post('/api/wallet/transferir', {
        'de'        : de,
        'para'      : para,
        'amount'    : amount,
        'assinatura': assinatura,
      });

  // ── Seed / Recuperação de Conta ──────────────────────────────────────────
  /// Ancora seed-backup ZK 22KB na rede: POST /api/wallet/seed-backup
  /// payload: string JSON com 22KB; seedHash: SHA-256(frase) — frase nunca enviada.
  static Future<Map<String, dynamic>?> seedBackup({
    required String plgAddress,
    required String payload,
    required String seedHash,
  }) =>
      _post('/api/wallet/seed-backup', {
        'plg_address': plgAddress,
        'seed_hash'  : seedHash,
        'payload'    : payload,
      });

  /// Consulta seed-backup por hash: GET /api/wallet/seed-backup?seed_hash=
  /// Aceita 200 (encontrado) e 404 (não encontrado com body JSON).
  static const List<String> _seedNodes = [
    'https://plegmadag.com',
    'https://usa.plegmadag.com',
    'https://mum.plegmadag.com',
    'https://sin.plegmadag.com',
  ];

  /// Recuperação de seed com fallback multi-servidor.
  /// Servidor 1 negativo → tenta os outros 3 antes de desistir.
  static Future<Map<String, dynamic>?> seedQuery(String seedHash) async {
    final path = '/api/wallet/seed-backup?seed_hash=$seedHash';

    for (final nodeBase in _seedNodes) {
      try {
        final res = await _client
            .get(Uri.parse('$nodeBase$path'))
            .timeout(Duration(seconds: _timeout));
        if (res.statusCode == 200) {
          final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
          if (data['ok'] == true) return data;
        }
        // 404 neste nó → tenta próximo
      } catch (e) {
        debugPrint('[seedQuery] $nodeBase falhou: $e');
      }
    }
    return {'ok': false, 'error': 'Backup nao encontrado em nenhum servidor da rede.'};
  }

  // ── Miner (novos endpoints) ───────────────────────────────────────────────
  /// Status do minerador por endereço: GET /api/miner/status?address=
  static Future<Map<String, dynamic>?> getMinerStatus(String address) =>
      _get('/api/miner/status?address=$address');

  /// Pausa o minerador: POST /api/miner/pause
  static Future<Map<String, dynamic>?> pauseMiner(String address) =>
      _post('/api/miner/pause', {'address': address});

  /// Retoma o minerador: POST /api/miner/resume
  static Future<Map<String, dynamic>?> resumeMiner(String address) =>
      _post('/api/miner/resume', {'address': address});

  // ── Auth (servidor auth_server.py porta 8082) ────────────────────────────
  // auth_server.py é o servidor autoritativo de QR auth (Dilithium3).
  // Sempre usa plegmadag.com (IP fixo EUR) para garantir que challenge e verify
  // chegam ao mesmo nó — api.plegmadag.com usa round-robin entre 4 servidores.
  static const String _authFixed = 'https://plegmadag.com';
  static String get _authBase => _isIp(_host)
      ? 'http://$_host:8082'
      : _authFixed;

  /// Gera desafio QR: GET /api/auth/challenge → auth_server.py (porta 8082)
  /// Retorna: {nonce, expires_in, site, message: "plegma://auth?nonce=XXX"}
  static Future<Map<String, dynamic>?> getAuthChallenge(String address) =>
      get('$_authBase/api/auth/challenge');

  static Future<Map<String, dynamic>?> authChallenge() =>
      get('$_authBase/api/auth/challenge');

  static Future<Map<String, dynamic>?> authVerify({
    required String nonce,
    required String plgAddress,
    required String signature,
    required String publicKey,
  }) =>
      post('$_authBase/api/auth/verify', {
        'nonce'      : nonce,
        'plg_address': plgAddress,
        'signature'  : signature,
        'public_key' : publicKey,
      });

  static Future<Map<String, dynamic>?> authStatus(String nonce) =>
      get('$_authBase/api/auth/status?nonce=$nonce');

  // ── Admin Console (porta 8080 / core_api) ────────────────────────────────
  static Future<Map<String, dynamic>?> adminAuthPending() =>
      _get('/api/admin/auth/pending');

  static Future<Map<String, dynamic>?> adminAuthVerify({
    required String nonce,
    required String plgAddress,
    required String signature,
    required String publicKey,
  }) =>
      post('$baseUrl/api/admin/auth/verify', {
        'nonce'    : nonce,
        'address'  : plgAddress,
        'signature': signature,
        'pubkey'   : publicKey,
      });

  // ── Lattice Shield (porta 8085) ───────────────────────────────────────────
  static String get _shieldBase => _host.contains('.') && !_isIp(_host)
      ? 'https://$_host'
      : 'http://$_host:8085';

  /// Status do Shield: GET /shield/status
  static Future<Map<String, dynamic>?> shieldStatus() =>
      get('$_shieldBase/shield/status');

  /// Verifica uma URL contra o banco de phishing: POST /shield/scan/url
  static Future<Map<String, dynamic>?> shieldScanUrl(String url) =>
      post('$_shieldBase/shield/scan/url', {'url': url});

  /// Verifica lote de apps contra o banco de malware: POST /shield/scan/batch
  static Future<Map<String, dynamic>?> shieldScanBatch(
      List<Map<String, String>> apps) =>
      post('$_shieldBase/shield/scan/batch', {'apps': apps});

  /// Reporta nova ameaça à inteligência coletiva: POST /shield/report
  static Future<Map<String, dynamic>?> shieldReport(
      String tipo, String valor) =>
      post('$_shieldBase/shield/report', {'tipo': tipo, 'valor': valor});

  /// Ancora snapshot ZK na rede: POST /shield/anchor
  static Future<Map<String, dynamic>?> shieldAnchor({
    required String stateHash,
    required String plgAddress,
    required int    appCount,
  }) =>
      post('$_shieldBase/shield/anchor', {
        'state_hash' : stateHash,
        'plg_address': plgAddress,
        'app_count'  : appCount,
      });

  /// Verifica um anchor existente: GET /shield/anchor/<id>
  static Future<Map<String, dynamic>?> shieldVerifyAnchor(String anchorId) =>
      get('$_shieldBase/shield/anchor/$anchorId');

  /// Verifica elegibilidade de pagamento: GET /shield/payment/check?address=
  static Future<Map<String, dynamic>?> shieldPaymentCheck(String plgAddress) =>
      get('$_shieldBase/shield/payment/check?address=$plgAddress');

  /// Ativa o Lattice Shield com método de pagamento: POST /shield/subscribe
  /// metodo: "gratis_genesis" | "carteira" | "mineracao"
  static Future<Map<String, dynamic>?> shieldSubscribe(
    String plgAddress, {
    String metodo = 'gratis_genesis',
    String txId   = '',
  }) =>
      post('$_shieldBase/shield/subscribe', {
        'plg_address'      : plgAddress,
        'metodo_pagamento' : metodo,
        if (txId.isNotEmpty) 'tx_id': txId,
      });

  /// Consulta status da assinatura: GET /shield/subscription/<address>
  static Future<Map<String, dynamic>?> shieldGetSubscription(String plgAddress) =>
      get('$_shieldBase/shield/subscription/$plgAddress');

  /// Cancela a assinatura: POST /shield/unsubscribe
  static Future<Map<String, dynamic>?> shieldUnsubscribe(String plgAddress) =>
      post('$_shieldBase/shield/unsubscribe', {'plg_address': plgAddress});

  // ── Plegma Timestamp — callback de confirmação de pagamento ─────────────
  /// Notifica o Plegma Timestamp que o pagamento foi confirmado on-chain.
  /// Chamado após transferência PLG bem-sucedida com [plgTxHash].
  static Future<bool> confirmTimestampPayment({
    required String callbackUrl,
    required String sessionId,
    required String plgTxHash,
    required String fromWallet,
    required double amount,
  }) async {
    try {
      final res = await _client
          .post(
            Uri.parse(callbackUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'session_id' : sessionId,
              'plg_tx_hash': plgTxHash,
              'from_wallet': fromWallet,
              'amount'     : amount.toStringAsFixed(6),
            }),
          )
          .timeout(const Duration(seconds: 15));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('Timestamp callback erro: $e');
      return false;
    }
  }

  // ── Helpers públicos (retrocompatibilidade) ───────────────────────────────
  static Future<Map<String, dynamic>?> get(String url) async {
    try {
      final res = await _client
          .get(Uri.parse(url))
          .timeout(Duration(seconds: _timeout));
      if (res.statusCode == 200) {
        return jsonDecode(utf8.decode(res.bodyBytes));
      }
    } catch (e) { debugPrint('Erro: $e'); }
    return null;
  }

  static Future<Map<String, dynamic>?> post(
      String url, Map<String, dynamic> body) async {
    try {
      final res = await _client
          .post(
            Uri.parse(url),
            headers: {'Content-Type': 'application/json'},
            body   : jsonEncode(body),
          )
          .timeout(Duration(seconds: _timeout));
      
      try {
        final Map<String, dynamic> decoded = jsonDecode(utf8.decode(res.bodyBytes));
        if (res.statusCode >= 400) {
          decoded['http_status'] = res.statusCode;
        }
        return decoded;
      } catch (_) {
        if (res.statusCode >= 200 && res.statusCode < 300) return {};
      }
    } catch (e) { debugPrint('Erro: $e'); }
    return null;
  }

  // ── Helpers privados ──────────────────────────────────────────────────────
  static Future<Map<String, dynamic>?> _get(String path) =>
      get('$baseUrl$path');

  static Future<Map<String, dynamic>?> _post(
      String path, Map<String, dynamic> body) =>
      post('$baseUrl$path', body);

  // ── Compatibilidade de URL antiga (para código legado) ────────────────────
  /// Mantido apenas para não quebrar código que ainda referencia walletUrl.
  /// Não existe mais servidor separado — todos apontam para baseUrl.
  static String get walletUrl => baseUrl;
  static String get dagUrl    => baseUrl;
  static String get authUrl   => _authBase;
  static String get minerUrl  => baseUrl;

  // ── Pool Aerarium (wallet_server.py — porta 8083) ─────────────────────────
  static String get _poolBase => _host.contains('.') && !_isIp(_host)
      ? 'https://$_host'
      : 'http://$_host:8083';

  /// URL base pública do servidor pool (porta 8083) — usado por providers externos.
  static String get poolBaseUrl => _poolBase;

  /// Cotação atual da pool PLG/USDC: GET /pool/cotacao
  static Future<Map<String, dynamic>?> getPoolCotacao() =>
      get('$_poolBase/pool/cotacao');

  /// Status completo da pool: GET /pool/status
  static Future<Map<String, dynamic>?> getPoolStatus() =>
      get('$_poolBase/pool/status');

  /// Registra compra PLG com USDC: POST /pool/comprar
  static Future<Map<String, dynamic>?> comprarPlg(
      String plgAddress, double usdcAmount) =>
      post('$_poolBase/pool/comprar', {
        'plg_address': plgAddress,
        'usdc_amount': usdcAmount,
      });

  /// Registra venda PLG por USDC: POST /pool/vender
  static Future<Map<String, dynamic>?> venderPlg({
    required String plgAddress,
    required double plgAmount,
    required String polygonAddress,
  }) =>
      post('$_poolBase/pool/vender', {
        'plg_address'    : plgAddress,
        'plg_amount'     : plgAmount,
        'polygon_address': polygonAddress,
      });

  // ── Ofertas P2P PLG-G ────────────────────────────────────────────────────
  /// Cria oferta de venda P2P: POST /wallet/oferta_plgg
  static Future<Map<String, dynamic>?> criarOfertaPlgg({
    required String vendedor,
    required String comprador,
    required double amountPlgg,
    required double precoUnitario,
  }) =>
      post('$_poolBase/wallet/oferta_plgg', {
        'vendedor'       : vendedor,
        'comprador'      : comprador,
        'amount_plgg'    : amountPlgg,
        'preco_unitario' : precoUnitario,
      });

  /// Oferta recebida pendente: GET /wallet/oferta_plgg/pendente?address=
  static Future<Map<String, dynamic>?> getOfertaPendente(String address) =>
      get('$_poolBase/wallet/oferta_plgg/pendente?address=$address');

  /// Responde a uma oferta: POST /wallet/oferta_plgg/responder
  static Future<Map<String, dynamic>?> responderOferta({
    required String ofertaId,
    required String comprador,
    required bool   aceitar,
  }) =>
      post('$_poolBase/wallet/oferta_plgg/responder', {
        'oferta_id': ofertaId,
        'comprador': comprador,
        'aceitar'  : aceitar,
      });

  // ── Fase da Rede ──────────────────────────────────────────────────────────
  /// Fase atual (FASE_ZERO / GENESIS_ATIVO / MAINNET_PLENA): GET /api/rede/fase
  static Future<Map<String, dynamic>?> getRedeFase() =>
      _get('/api/rede/fase');

  /// Heartbeat / Node Discovery: POST /api/node/heartbeat
  /// [publicKey] e [signature] em formato hex — Dilithium3 obrigatório.
  static Future<Map<String, dynamic>?> nodeHeartbeat(
    String nodeId, {
    required String publicKey,
    required String signature,
    Map<String, dynamic>? metadata,
  }) =>
      _post('/api/node/heartbeat', {
        'node_id'   : nodeId,
        'public_key': publicKey,
        'signature' : signature,
        if (metadata != null) 'metadata': metadata,
      });
}
