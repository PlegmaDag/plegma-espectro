// ============================================================================
// WALLET MODEL — Modelos de dados da carteira
// ============================================================================

class WalletModel {
  final String plgAddress;
  final double disponivel;       // PLG mainnet (saldo_plg). 0 antes da Genesis.
  final double vestingLocked;
  final double totalEstimado;
  final double mineradoTotal;
  final double enviadoTotal;
  final double recebidoTotal;
  final double vestingValidator;
  final double vestingProver;
  final int    proversVinculados;
  final int?   proximaLiberacao;
  final double plgPreco;
  final double plgVariacao;

  // ── PLG-G (Governança Genesis) ────────────────────────────────────────────
  // Preço PLG-G: fixo $0.10 na Genesis; após Dia 31 reflete última venda P2P
  final double  plggTotal;       // saldo total PLG-G
  final double  plggLocked;      // PLG-G em lockup
  final double  plggAvailable;   // PLG-G disponível para P2P
  final String? plggUnlockDate;  // próximo unlock (ex: "2025-06-01")
  final String  categoria;              // MASTER / SENTINELA / APOIADOR
  final double  boostMineracao;         // 1.0 / 1.5 / 2.0
  final double  pesoVoto;               // 1.0 (nó comum) ou 1.01–5.0 (Sócio Genesis)

  // ── Selo Sócio Genesis — identificador único e intransferível ─────────────
  // Concedido na compra Genesis. Perdido permanentemente se saldo zera.
  // A governança viaja com o token; o selo NÃO.
  final bool    socioGenesis;           // participou da Genesis Reserve
  final bool    seloGenesisAtivo;       // selo ativo (tem PLG-G ≥ 1 e nunca zerou)
  final bool    statusGenesisPerdido;   // zerou o saldo — irrecuperável

  const WalletModel({
    required this.plgAddress,
    this.disponivel       = 0,
    this.vestingLocked    = 0,
    this.totalEstimado    = 0,
    this.mineradoTotal    = 0,
    this.enviadoTotal     = 0,
    this.recebidoTotal    = 0,
    this.vestingValidator = 0,
    this.vestingProver    = 0,
    this.proversVinculados= 0,
    this.proximaLiberacao ,
    this.plgPreco         = 0.0047,
    this.plgVariacao      = 0,
    // PLG-G defaults
    this.plggTotal        = 0,
    this.plggLocked       = 0,
    this.plggAvailable    = 0,
    this.plggUnlockDate   ,
    this.categoria             = 'APOIADOR',
    this.boostMineracao        = 1.0,
    this.pesoVoto              = 1.0,
    this.socioGenesis          = false,
    this.seloGenesisAtivo      = false,
    this.statusGenesisPerdido  = false,
  });

  double get disponivelUsdt  => disponivel    * plgPreco;
  double get vestingUsdt     => vestingLocked * plgPreco;
  double get totalUsdt       => totalEstimado * plgPreco;

  factory WalletModel.fromJson(Map<String, dynamic> j) => WalletModel(
    plgAddress        : j['plg_address']       ?? '',
    disponivel        : (j['disponivel']        ?? j['saldo_plg']  ?? 0).toDouble(),
    vestingLocked     : (j['vesting_locked']    ?? 0).toDouble(),
    totalEstimado     : (j['total_estimado']    ?? 0).toDouble(),
    mineradoTotal     : (j['minerado_total']    ?? 0).toDouble(),
    enviadoTotal      : (j['enviado_total']     ?? 0).toDouble(),
    recebidoTotal     : (j['recebido_total']    ?? 0).toDouble(),
    vestingValidator  : (j['vesting_validator'] ?? 0).toDouble(),
    vestingProver     : (j['vesting_prover']    ?? 0).toDouble(),
    proversVinculados : (j['provers_vinculados']?? 0).toInt(),
    proximaLiberacao  : j['proxima_liberacao'],
    // PLG-G — opcionais, vindos de getGenesisSaldo / getPriority
    plggTotal         : (j['plgg_total']        ?? 0).toDouble(),
    plggLocked        : (j['plgg_locked']       ?? 0).toDouble(),
    plggAvailable     : (j['plgg_available']    ?? 0).toDouble(),
    plggUnlockDate    : j['plgg_unlock_date'],
    categoria              : j['categoria']                  ?? 'APOIADOR',
    boostMineracao         : (j['boost_mineracao']           ?? 1.0).toDouble(),
    pesoVoto               : (j['peso_voto']                 ?? 1.0).toDouble(),
    socioGenesis           : j['socio_genesis']              ?? false,
    seloGenesisAtivo       : j['selo_genesis_ativo']         ?? false,
    statusGenesisPerdido   : j['status_genesis_perdido']     ?? false,
  );

  WalletModel copyWith({
    double? disponivel,
    double? vestingLocked,
    double? totalEstimado,
    double? plgPreco,
    double? plgVariacao,
    double? plggTotal,
    double? plggLocked,
    double? plggAvailable,
    String? plggUnlockDate,
    String? categoria,
    double? boostMineracao,
    double? pesoVoto,
    bool?   socioGenesis,
    bool?   seloGenesisAtivo,
    bool?   statusGenesisPerdido,
  }) =>
      WalletModel(
        plgAddress             : plgAddress,
        disponivel             : disponivel             ?? this.disponivel,
        vestingLocked          : vestingLocked          ?? this.vestingLocked,
        totalEstimado          : totalEstimado          ?? this.totalEstimado,
        mineradoTotal          : mineradoTotal,
        enviadoTotal           : enviadoTotal,
        recebidoTotal          : recebidoTotal,
        vestingValidator       : vestingValidator,
        vestingProver          : vestingProver,
        proversVinculados      : proversVinculados,
        proximaLiberacao       : proximaLiberacao,
        plgPreco               : plgPreco               ?? this.plgPreco,
        plgVariacao            : plgVariacao            ?? this.plgVariacao,
        plggTotal              : plggTotal              ?? this.plggTotal,
        plggLocked             : plggLocked             ?? this.plggLocked,
        plggAvailable          : plggAvailable          ?? this.plggAvailable,
        plggUnlockDate         : plggUnlockDate         ?? this.plggUnlockDate,
        categoria              : categoria              ?? this.categoria,
        boostMineracao         : boostMineracao         ?? this.boostMineracao,
        pesoVoto               : pesoVoto               ?? this.pesoVoto,
        socioGenesis           : socioGenesis           ?? this.socioGenesis,
        seloGenesisAtivo       : seloGenesisAtivo       ?? this.seloGenesisAtivo,
        statusGenesisPerdido   : statusGenesisPerdido   ?? this.statusGenesisPerdido,
      );
}

class VestingContrato {
  final double amount;
  final String releaseDate;
  final int    daysRemaining;
  final String nodeType;
  final String pool;
  final String status;

  const VestingContrato({
    required this.amount,
    required this.releaseDate,
    required this.daysRemaining,
    required this.nodeType,
    required this.pool,
    required this.status,
  });

  factory VestingContrato.fromJson(Map<String, dynamic> j) => VestingContrato(
    amount        : (j['amount']         ?? 0).toDouble(),
    releaseDate   : j['release_date']    ?? '',
    daysRemaining : (j['days_remaining'] ?? 0).toInt(),
    nodeType      : j['node_type']       ?? '',
    pool          : j['pool']            ?? '',
    status        : j['status']          ?? '',
  );

  bool get isLocked => status == 'BLOQUEADO';
}

class TransacaoHistorico {
  final String txId;
  final String tipo;
  final double amount;
  final String contraparte;
  final String data;
  final String status;
  final String fonte;
  final String releaseDate;

  const TransacaoHistorico({
    required this.txId,
    required this.tipo,
    required this.amount,
    required this.contraparte,
    required this.data,
    required this.status,
    this.fonte       = '',
    this.releaseDate = '',
  });

  factory TransacaoHistorico.fromJson(Map<String, dynamic> j) => TransacaoHistorico(
    txId        : j['tx_id']       ?? '',
    tipo        : j['tipo']        ?? '',
    amount      : (j['amount']     ?? 0).toDouble(),
    contraparte : j['contraparte'] ?? '',
    data        : j['data']        ?? '',
    status      : j['status']      ?? '',
    fonte       : j['fonte']       ?? '',
    releaseDate : j['release_date']?.toString() ?? '',
  );

  bool get isEntrada => tipo != 'ENVIADO';
}

// ── Oferta P2P de PLG-G ───────────────────────────────────────────────────────
class OfertaP2P {
  final String ofertaId;
  final String vendedor;
  final String comprador;
  final double amountPlgg;
  final double precoUnitario; // USDC por PLG-G
  final double totalUsdc;
  final String expiracao;
  final String status; // PENDENTE | ACEITA | REJEITADA | EXPIRADA

  const OfertaP2P({
    required this.ofertaId,
    required this.vendedor,
    required this.comprador,
    required this.amountPlgg,
    required this.precoUnitario,
    required this.totalUsdc,
    required this.expiracao,
    required this.status,
  });

  factory OfertaP2P.fromJson(Map<String, dynamic> j) => OfertaP2P(
    ofertaId      : j['oferta_id']      ?? '',
    vendedor      : j['vendedor']       ?? '',
    comprador     : j['comprador']      ?? '',
    amountPlgg    : (j['amount_plgg']   ?? 0).toDouble(),
    precoUnitario : (j['preco_unitario']?? 0).toDouble(),
    totalUsdc     : (j['total_usdc']    ?? 0).toDouble(),
    expiracao     : j['expiracao']      ?? '',
    status        : j['status']         ?? 'PENDENTE',
  );
}

class ProverVinculado {
  final String nodeId;
  final String categoria;
  final int    score;
  final bool   ativo;
  final double ganhos;
  final String ultimoPing;

  const ProverVinculado({
    required this.nodeId,
    required this.categoria,
    required this.score,
    required this.ativo,
    required this.ganhos,
    required this.ultimoPing,
  });

  factory ProverVinculado.fromJson(Map<String, dynamic> j) => ProverVinculado(
    nodeId    : j['node_id']      ?? '',
    categoria : j['categoria']    ?? '',
    score     : (j['score']       ?? 0).toInt(),
    ativo     : j['ativo']        ?? false,
    ganhos    : (j['ganhos_total']?? 0).toDouble(),
    ultimoPing: j['ultimo_ping']  ?? '',
  );
}
