import 'package:flutter/material.dart';

// ============================================================================
// APP LOCALIZATIONS — Internacionalização PLEGMA
// Adapta automaticamente ao idioma do dispositivo.
// Adicionar novos idiomas: criar nova entrada no mapa _strings.
// ============================================================================

class AppLocalizations {
  final Locale locale;
  AppLocalizations(this.locale);

  static AppLocalizations of(BuildContext context) =>
      Localizations.of<AppLocalizations>(context, AppLocalizations)!;

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  // ── Strings por idioma ────────────────────────────────────────────────────
  static final Map<String, Map<String, String>> _strings = {

    // ── Português Brasil (padrão) ──────────────────────────────────────────
    'pt': {
      // Geral
      'app_name'            : 'PLEGMA',
      'tagline'             : 'Soberania Digital',
      'ok'                  : 'OK',
      'cancel'              : 'CANCELAR',
      'confirm'             : 'CONFIRMAR',
      'close'               : 'FECHAR',
      'save'                : 'SALVAR',
      'back'                : 'VOLTAR',
      'loading'             : 'Carregando...',
      'error'               : 'Erro',
      'success'             : 'Sucesso',
      'offline'             : 'Servidor offline',
      'online'              : 'ONLINE',
      'active'              : 'ATIVO',
      'inactive'            : 'INATIVO',

      // Boot
      'boot_checking'       : 'Verificando carteira...',
      'boot_entropy'        : 'Coletando entropia do hardware...',
      'boot_generating'     : 'Gerando par de chaves Dilithium3...',
      'boot_binding'        : 'Vinculando identidade ao dispositivo...',
      'boot_finalizing'     : 'Finalizando...',
      'boot_done'           : 'Carteira criada ✓',
      'boot_server_ip'      : 'IP DO SERVIDOR',
      'boot_server_hint'    : 'IP do computador onde os servidores Python estão rodando.',
      'boot_enter_network'  : 'ENTRAR NA REDE →',

      // Nav
      'nav_network'         : 'REDE',
      'nav_wallet'          : 'WALLET',
      'nav_validator'       : 'VALIDADOR',
      'nav_shield'          : 'SHIELD',
      'nav_provers'         : 'PROVERS',
      'nav_governance'      : 'GOVERNANÇA',

      // Home
      'home_available'      : 'Saldo Disponível',
      'home_vesting'        : 'Em Vesting',
      'home_hashrate'       : 'Hashrate',
      'home_active_nodes'   : 'Nós Ativos',
      'home_provers'        : 'Provers',
      'home_last_vertex'    : 'Último Vértice DAG',
      'home_uptime'         : 'Uptime',
      'home_pools'          : 'Divisão de Incentivos — Estatuto §13',
      'home_release_in'     : 'Libera em',
      'home_days'           : 'd',

      // Wallet
      'wallet_balance'      : 'SALDO',
      'wallet_vesting'      : 'VESTING',
      'wallet_history'      : 'EXTRATO',
      'wallet_price'        : '\$PLG / USDT',
      'wallet_pre_listing'  : 'PRÉ-LISTAGEM',
      'wallet_available'    : 'DISPONÍVEL',
      'wallet_locked'       : 'EM VESTING (30d)',
      'wallet_total'        : 'TOTAL ESTIMADO',
      'wallet_pools'        : 'Pools de Vesting',
      'wallet_send'         : 'ENVIAR \$PLG',
      'wallet_dest'         : 'Endereço PLG Destino',
      'wallet_amount'       : 'Valor (\$PLG)',
      'wallet_sign_send'    : 'ASSINAR E ENVIAR',
      'wallet_sent_ok'      : '✓ Enviado com sucesso',
      'wallet_filter_all'   : 'TODAS',
      'wallet_filter_recv'  : 'RECEBIDAS',
      'wallet_filter_sent'  : 'ENVIADAS',
      'wallet_filter_mined' : 'MINERADAS',
      'wallet_no_tx'        : 'Nenhuma transação',
      'wallet_no_vesting'   : 'Nenhum vesting pendente',
      'wallet_copied'       : 'Endereço copiado',

      // Validator
      'validator_mining'    : 'MINERANDO',
      'validator_paused'    : 'PAUSADO',
      'validator_tap_pause' : 'Toque para pausar',
      'validator_tap_start' : 'Toque para iniciar',
      'validator_hashrate'  : 'Hashrate',
      'validator_reward'    : 'Recompensa',
      'validator_accepted'  : 'Vértices Aceitos',
      'validator_uptime'    : 'Uptime',
      'validator_dag'       : 'Status da DAG',
      'validator_nodes'     : 'Nós Ativos',
      'validator_last_hash' : 'Último Hash',
      'validator_pool'      : 'Pool',
      'validator_clause14'  : 'Cláusula 14ª — Justiça Computacional',
      'validator_clause14_desc': 'A potência de hardware não confere prioridade de validação. O trabalho é distribuído equitativamente entre os Provers disponíveis, com teto de 10% por nó.',

      // Shield
      'shield_algorithm'    : 'Algoritmo de Assinatura',
      'shield_address'      : 'Endereço PLG',
      'shield_auth_title'   : 'Autenticar no Dashboard',
      'shield_auth_desc'    : 'Escaneie o QR Code exibido no site para autenticar com Dilithium3. A chave privada nunca sai do dispositivo.',
      'shield_scan_qr'      : 'ESCANEAR QR',
      'shield_protections'  : 'Proteções Ativas',
      'shield_qr_prompt'    : 'Aponte para o QR do Dashboard',
      'shield_qr_invalid'   : 'QR inválido — não é um QR PLEGMA',
      'shield_auth_ok'      : '✓ Autenticado com sucesso!',
      'shield_auth_fail'    : '✗ Verificação falhou',
      'shield_reading_qr'   : 'Lendo QR...',
      'shield_biometry'     : 'Confirmando biometria...',
      'shield_signing'      : 'Assinando com Dilithium3...',
      'shield_verifying'    : 'Verificando no servidor...',
      'shield_imei'         : 'Vínculo Chave + Dispositivo',
      'shield_tx_sig'       : 'Assinatura de Transações',
      'shield_qr_bio'       : 'Auth QR + Biometria',
      'shield_panic_pin'    : 'PIN de Pânico',
      'shield_pact5'        : 'Pacto dos 5 Nós',
      'shield_ghost'        : 'Tela Fantasma',

      // Provers
      'provers_active'      : 'Provers Ativos',
      'provers_total_earn'  : 'Ganhos Totais',
      'provers_how_title'   : 'Como Vincular um Prover',
      'provers_step1'       : 'Baixe e execute o PLEGMA_Minerador.exe no PC',
      'provers_step2'       : 'O minerador detecta o hardware e gera um QR de vínculo',
      'provers_step3'       : 'Toque em + e escaneie o QR com este app',
      'provers_step4'       : 'As recompensas vão direto para este endereço PLG',
      'provers_empty'       : 'Nenhum Prover vinculado.\nEscaneie o QR do minerador para adicionar.',
      'provers_qr_prompt'   : 'Aponte para o QR de vínculo do minerador',
      'provers_qr_invalid'  : 'QR inválido — não é um QR de vínculo PLEGMA',
      'provers_bind_ok'     : '✓ Prover vinculado com sucesso!',
      'provers_bind_fail'   : '✗ Falha ao vincular — tente novamente',
      'provers_remove'      : 'REMOVER',
      'provers_remove_title': 'Desvincular Prover',
      'provers_remove_desc' : 'Ele perderá acesso até ser vinculado novamente.',
      'provers_removed'     : 'Prover desvinculado',
      'provers_clause14'    : 'Cláusula 14ª: Teto de 10% do trabalho por Prover — Estatuto §13',

      // Governance
      'gov_quorum_waiting'  : 'Aguardando Quórum',
      'gov_quorum_active'   : 'Governança Ativa',
      'gov_quorum_reached'  : 'Quórum atingido. Governança comunitária ativa.',
      'gov_nodes_missing'   : 'nós restantes',
      'gov_mobile_vote'     : 'Voto Exclusivo do Nó Móvel',
      'gov_mobile_vote_desc': 'Apenas o dispositivo móvel com carteira activa pode assinar propostas e votar.',
      'gov_sybil'           : 'Proteção Sybil',
      'gov_sybil_desc'      : 'A assinatura Dilithium3 vinculada à carteira impede múltiplas instâncias de votação.',
      'gov_justice'         : 'Justiça Algorítmica',
      'gov_justice_desc'    : 'Potência de hardware não confere maior peso de voto.',
      'gov_quorum_rule'     : 'Quórum Mínimo',
      'gov_quorum_desc'     : 'Nenhuma proposta pode ser votada sem 10.000 nós ativos na rede.',
      'gov_proposals'       : 'Propostas — V2.0+',
      'gov_blocked'         : 'BLOQUEADO',
      'gov_nodes_remaining' : 'NÓS RESTANTES',
    },

    // ── English ────────────────────────────────────────────────────────────
    'en': {
      'app_name'            : 'PLEGMA',
      'tagline'             : 'Digital Sovereignty',
      'ok'                  : 'OK',
      'cancel'              : 'CANCEL',
      'confirm'             : 'CONFIRM',
      'close'               : 'CLOSE',
      'save'                : 'SAVE',
      'back'                : 'BACK',
      'loading'             : 'Loading...',
      'error'               : 'Error',
      'success'             : 'Success',
      'offline'             : 'Server offline',
      'online'              : 'ONLINE',
      'active'              : 'ACTIVE',
      'inactive'            : 'INACTIVE',

      'boot_checking'       : 'Checking wallet...',
      'boot_entropy'        : 'Collecting hardware entropy...',
      'boot_generating'     : 'Generating Dilithium3 key pair...',
      'boot_binding'        : 'Binding identity to device...',
      'boot_finalizing'     : 'Finalizing...',
      'boot_done'           : 'Wallet created ✓',
      'boot_server_ip'      : 'SERVER IP',
      'boot_server_hint'    : 'IP of the computer running the Python servers.',
      'boot_enter_network'  : 'JOIN NETWORK →',

      'nav_network'         : 'NETWORK',
      'nav_wallet'          : 'WALLET',
      'nav_validator'       : 'VALIDATOR',
      'nav_shield'          : 'SHIELD',
      'nav_provers'         : 'PROVERS',
      'nav_governance'      : 'GOVERNANCE',

      'home_available'      : 'Available Balance',
      'home_vesting'        : 'In Vesting',
      'home_hashrate'       : 'Hashrate',
      'home_active_nodes'   : 'Active Nodes',
      'home_provers'        : 'Provers',
      'home_last_vertex'    : 'Last DAG Vertex',
      'home_uptime'         : 'Uptime',
      'home_pools'          : 'Incentive Split — Statute §13',
      'home_release_in'     : 'Releases in',
      'home_days'           : 'd',

      'wallet_balance'      : 'BALANCE',
      'wallet_vesting'      : 'VESTING',
      'wallet_history'      : 'HISTORY',
      'wallet_price'        : '\$PLG / USDT',
      'wallet_pre_listing'  : 'PRE-LISTING',
      'wallet_available'    : 'AVAILABLE',
      'wallet_locked'       : 'IN VESTING (30d)',
      'wallet_total'        : 'TOTAL ESTIMATED',
      'wallet_pools'        : 'Vesting Pools',
      'wallet_send'         : 'SEND \$PLG',
      'wallet_dest'         : 'Destination PLG Address',
      'wallet_amount'       : 'Amount (\$PLG)',
      'wallet_sign_send'    : 'SIGN AND SEND',
      'wallet_sent_ok'      : '✓ Sent successfully',
      'wallet_filter_all'   : 'ALL',
      'wallet_filter_recv'  : 'RECEIVED',
      'wallet_filter_sent'  : 'SENT',
      'wallet_filter_mined' : 'MINED',
      'wallet_no_tx'        : 'No transactions',
      'wallet_no_vesting'   : 'No pending vesting',
      'wallet_copied'       : 'Address copied',

      'validator_mining'    : 'MINING',
      'validator_paused'    : 'PAUSED',
      'validator_tap_pause' : 'Tap to pause',
      'validator_tap_start' : 'Tap to start',
      'validator_hashrate'  : 'Hashrate',
      'validator_reward'    : 'Reward',
      'validator_accepted'  : 'Accepted Vertices',
      'validator_uptime'    : 'Uptime',
      'validator_dag'       : 'DAG Status',
      'validator_nodes'     : 'Active Nodes',
      'validator_last_hash' : 'Last Hash',
      'validator_pool'      : 'Pool',
      'validator_clause14'  : 'Clause 14 — Computational Justice',
      'validator_clause14_desc': 'Hardware power does not grant validation priority. Work is distributed equitably among available Provers, with a cap of 10% per node.',

      'shield_algorithm'    : 'Signature Algorithm',
      'shield_address'      : 'PLG Address',
      'shield_auth_title'   : 'Authenticate on Dashboard',
      'shield_auth_desc'    : 'Scan the QR Code displayed on the site to authenticate with Dilithium3. The private key never leaves the device.',
      'shield_scan_qr'      : 'SCAN QR',
      'shield_protections'  : 'Active Protections',
      'shield_qr_prompt'    : 'Point at the Dashboard QR',
      'shield_qr_invalid'   : 'Invalid QR — not a PLEGMA QR',
      'shield_auth_ok'      : '✓ Authenticated successfully!',
      'shield_auth_fail'    : '✗ Verification failed',
      'shield_reading_qr'   : 'Reading QR...',
      'shield_biometry'     : 'Confirming biometrics...',
      'shield_signing'      : 'Signing with Dilithium3...',
      'shield_verifying'    : 'Verifying on server...',
      'shield_imei'         : 'Key + Device Binding',
      'shield_tx_sig'       : 'Transaction Signing',
      'shield_qr_bio'       : 'QR Auth + Biometrics',
      'shield_panic_pin'    : 'Panic PIN',
      'shield_pact5'        : 'Pact of 5 Nodes',
      'shield_ghost'        : 'Ghost Screen',

      'provers_active'      : 'Active Provers',
      'provers_total_earn'  : 'Total Earnings',
      'provers_how_title'   : 'How to Link a Prover',
      'provers_step1'       : 'Download and run PLEGMA_Minerador.exe on the PC',
      'provers_step2'       : 'The miner detects hardware and generates a binding QR',
      'provers_step3'       : 'Tap + and scan the QR with this app',
      'provers_step4'       : 'Rewards go directly to this PLG address',
      'provers_empty'       : 'No Provers linked.\nScan the miner QR to add one.',
      'provers_qr_prompt'   : 'Point at the miner binding QR',
      'provers_qr_invalid'  : 'Invalid QR — not a PLEGMA binding QR',
      'provers_bind_ok'     : '✓ Prover linked successfully!',
      'provers_bind_fail'   : '✗ Linking failed — please try again',
      'provers_remove'      : 'REMOVE',
      'provers_remove_title': 'Unlink Prover',
      'provers_remove_desc' : 'It will lose access until linked again.',
      'provers_removed'     : 'Prover unlinked',
      'provers_clause14'    : 'Clause 14: 10% work cap per Prover — Statute §13',

      'gov_quorum_waiting'  : 'Awaiting Quorum',
      'gov_quorum_active'   : 'Governance Active',
      'gov_quorum_reached'  : 'Quorum reached. Community governance active.',
      'gov_nodes_missing'   : 'nodes remaining',
      'gov_mobile_vote'     : 'Exclusive Mobile Node Vote',
      'gov_mobile_vote_desc': 'Only the mobile device with an active wallet can sign proposals and vote.',
      'gov_sybil'           : 'Sybil Protection',
      'gov_sybil_desc'      : 'Dilithium3 wallet-bound signatures prevent multiple voting instances.',
      'gov_justice'         : 'Algorithmic Justice',
      'gov_justice_desc'    : 'Hardware power does not grant greater voting weight.',
      'gov_quorum_rule'     : 'Minimum Quorum',
      'gov_quorum_desc'     : 'No proposal can be voted on without 10,000 active nodes.',
      'gov_proposals'       : 'Proposals — V2.0+',
      'gov_blocked'         : 'LOCKED',
      'gov_nodes_remaining' : 'NODES REMAINING',
    },

    // ── Español ────────────────────────────────────────────────────────────
    'es': {
      'app_name'            : 'PLEGMA',
      'tagline'             : 'Soberanía Digital',
      'ok'                  : 'OK',
      'cancel'              : 'CANCELAR',
      'loading'             : 'Cargando...',
      'online'              : 'EN LÍNEA',
      'active'              : 'ACTIVO',
      'boot_checking'       : 'Verificando billetera...',
      'boot_generating'     : 'Generando par de claves Dilithium3...',
      'boot_done'           : 'Billetera creada ✓',
      'boot_enter_network'  : 'UNIRSE A LA RED →',
      'nav_network'         : 'RED',
      'nav_wallet'          : 'BILLETERA',
      'nav_validator'       : 'VALIDADOR',
      'nav_shield'          : 'ESCUDO',
      'nav_provers'         : 'PROBADORES',
      'nav_governance'      : 'GOBERNANZA',
      'home_available'      : 'Saldo Disponible',
      'validator_mining'    : 'MINANDO',
      'validator_paused'    : 'PAUSADO',
      'wallet_send'         : 'ENVIAR \$PLG',
      'shield_scan_qr'      : 'ESCANEAR QR',
      'gov_blocked'         : 'BLOQUEADO',
    },

    // ── Français ───────────────────────────────────────────────────────────
    'fr': {
      'app_name'            : 'PLEGMA',
      'tagline'             : 'Souveraineté Numérique',
      'ok'                  : 'OK',
      'cancel'              : 'ANNULER',
      'loading'             : 'Chargement...',
      'online'              : 'EN LIGNE',
      'active'              : 'ACTIF',
      'boot_checking'       : 'Vérification du portefeuille...',
      'boot_generating'     : 'Génération de la paire de clés Dilithium3...',
      'boot_done'           : 'Portefeuille créé ✓',
      'boot_enter_network'  : 'REJOINDRE LE RÉSEAU →',
      'nav_network'         : 'RÉSEAU',
      'nav_wallet'          : 'PORTEFEUILLE',
      'nav_validator'       : 'VALIDATEUR',
      'nav_shield'          : 'BOUCLIER',
      'nav_provers'         : 'PROUVEURS',
      'nav_governance'      : 'GOUVERNANCE',
      'home_available'      : 'Solde Disponible',
      'validator_mining'    : 'MINAGE',
      'validator_paused'    : 'EN PAUSE',
      'wallet_send'         : 'ENVOYER \$PLG',
      'shield_scan_qr'      : 'SCANNER QR',
      'gov_blocked'         : 'BLOQUÉ',
    },
  };

  // ── Lookup com fallback pt → en ───────────────────────────────────────────
  String get(String key) {
    final lang = locale.languageCode;
    return _strings[lang]?[key]
        ?? _strings['en']?[key]
        ?? _strings['pt']?[key]
        ?? key;
  }

  // ── Atalho estático ───────────────────────────────────────────────────────
  static String t(BuildContext context, String key) =>
      AppLocalizations.of(context).get(key);
}

// ── Delegate ──────────────────────────────────────────────────────────────────
class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {

  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) => [
    'pt', 'en', 'es', 'fr', 'de', 'zh', 'ja', 'ko', 'ar', 'ru'
  ].contains(locale.languageCode);

  @override
  Future<AppLocalizations> load(Locale locale) async =>
      AppLocalizations(locale);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
