import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../services/dilithium_ffi_service.dart';
import '../../services/seed_service.dart';
import '../../services/storage_service.dart';
import '../../theme/plegma_theme.dart';
import '../../widgets/plegma_card.dart';

// ============================================================================
// RecoverAccountScreen — Recuperação de conta via seed phrase (12 palavras)
//
// Fluxo:
//   1. Usuário digita as 12 palavras na ordem original
//   2. App calcula BLAKE3("plegma_seed_v1_" + frase) localmente
//   3. Consulta GET /api/wallet/seed-backup?seed_hash=<hex>
//   4. Se encontrado → salva PLG address + seed localmente → botão ENTRAR
//   5. As palavras JAMAIS saem do dispositivo em claro
// ============================================================================

class RecoverAccountScreen extends StatefulWidget {
  const RecoverAccountScreen({super.key});

  @override
  State<RecoverAccountScreen> createState() => _RecoverAccountScreenState();
}

class _RecoverAccountScreenState extends State<RecoverAccountScreen> {
  final List<TextEditingController> _ctrl =
      List.generate(12, (_) => TextEditingController());
  final List<FocusNode> _focus = List.generate(12, (_) => FocusNode());

  bool    _consultando  = false;
  bool    _encontrado   = false;
  bool    _restaurando  = false;
  String? _plgAddress;
  String? _anchorId;
  int?    _createdAt;
  String? _skEncB64;   // chave privada encriptada (v2 backup)
  String? _pkB64;      // chave pública (v2 backup)
  bool    _semChaves   = false; // backup v1 sem chaves — modo leitura
  String? _erro;
  String  _servidorAtual = ApiService.defaultHost;

  @override
  void initState() {
    super.initState();
    _carregarServidor();
  }

  Future<void> _carregarServidor() async {
    final host = await StorageService.lerHost();
    if (mounted) setState(() => _servidorAtual = host);
  }

  @override
  void dispose() {
    for (final c in _ctrl)  c.dispose();
    for (final f in _focus) f.dispose();
    super.dispose();
  }

  Future<String> _computeHash(List<String> words) async {
    final phrase = words.join(' ');
    final bytes  = Uint8List.fromList(utf8.encode('plegma_seed_v1_$phrase'));
    final hash   = await DilithiumFfiService.instance.blake3HashAsync(bytes);
    return DilithiumFfiService.bytesToHex(hash);
  }

  Future<void> _consultar() async {
    FocusScope.of(context).unfocus();
    final words = _ctrl.map((c) => c.text.trim().toLowerCase()).toList();

    if (words.any((w) => w.isEmpty)) {
      setState(() => _erro = 'Preencha todas as 12 palavras.');
      return;
    }

    setState(() {
      _consultando = true;
      _encontrado  = false;
      _erro        = null;
      _plgAddress  = null;
    });

    final hash   = await _computeHash(words);
    final result = await ApiService.seedQuery(hash);

    if (!mounted) return;

    if (result != null && result['ok'] == true) {
      final raw = result['created_at'];

      // Tenta extrair chaves encriptadas do payload (backup v2)
      String? skEnc;
      String? pk;
      try {
        final payloadStr = result['payload'] as String?;
        if (payloadStr != null && payloadStr.isNotEmpty) {
          final inner = jsonDecode(payloadStr.trim()) as Map<String, dynamic>;
          skEnc = inner['sk_enc_b64'] as String?;
          pk    = inner['pk_b64']     as String?;
        }
      } catch (e) { debugPrint('Erro: $e'); }

      setState(() {
        _consultando = false;
        _encontrado  = true;
        _plgAddress  = result['plg_address']?.toString();
        _anchorId    = result['anchor_id']?.toString();
        _createdAt   = raw is int ? raw : int.tryParse(raw?.toString() ?? '');
        _skEncB64    = skEnc;
        _pkB64       = pk;
        _semChaves   = skEnc == null || pk == null;
        _erro        = null;
      });
    } else if (result == null) {
      setState(() {
        _consultando = false;
        _erro = 'Servidor indisponível. Verifique sua conexão ou configure '
            'o servidor correto no menu lateral do app.';
      });
    } else {
      setState(() {
        _consultando = false;
        _erro = 'Seed phrase não encontrada em $_servidorAtual.\n'
            'Se gerou a carteira com um servidor diferente, configure-o '
            'no menu lateral do app e tente novamente.';
      });
    }
  }

  /// Restaura PLG address, chaves criptográficas e seed phrase localmente.
  Future<void> _restaurarConta() async {
    if (_plgAddress == null) return;
    setState(() => _restaurando = true);

    final words = _ctrl.map((c) => c.text.trim().toLowerCase()).toList();

    // Persiste endereço e seed
    await StorageService.salvarEndereco(_plgAddress!);
    await StorageService.salvarHost(_servidorAtual);
    await StorageService.marcarOnboardingCompleto();
    await SeedService.salvar(words);

    // Restaura chave privada (decriptada) e pública se disponíveis no backup v2
    if (_skEncB64 != null && _pkB64 != null) {
      try {
        final seedHash = await _computeHash(words);
        final skB64    = await SeedService.encriptarOuDecriptarChave(_skEncB64!, seedHash);
        await StorageService.salvarChavePrivada(skB64);
        await StorageService.salvarChavePublica(_pkB64!);
      } catch (_) {
        // Falha silenciosa — app entra em modo leitura
      }
    }

    // Gap 1: limpa padrão B2 existente — usuário define novo padrão a seguir
    await AuthService.clearPattern();

    // Bloqueia imediatamente — HomeScreen exigirá biometria
    AuthService.lock();

    if (!mounted) return;
    // Remove toda a pilha de navegação e vai para setup do padrão B2
    Navigator.of(context).pushNamedAndRemoveUntil('/pattern-setup', (_) => false);
  }

  void _copiarEndereco() {
    if (_plgAddress == null) return;
    Clipboard.setData(ClipboardData(text: _plgAddress!));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
          content: Text('Endereço copiado'),
          duration: Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      appBar: AppBar(
        backgroundColor: PlegmaColors.bg,
        title: const Text('RECUPERAR CONTA',
            style: TextStyle(letterSpacing: 3, fontSize: 13)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [

          // ── Aviso de privacidade ────────────────────────────────────────────
          PlegmaCard(
            topAccent: PlegmaColors.amber,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const PlegmaLabel('Frase de Recuperação — 12 palavras',
                    color: PlegmaColors.amber),
                const SizedBox(height: 8),
                const Text(
                  'Digite as palavras na ordem exata em que foram apresentadas. '
                  'O cálculo é feito localmente — as palavras jamais saem do dispositivo. '
                  'Apenas o hash BLAKE3 é consultado na rede.',
                  style: TextStyle(
                      fontSize: 11, color: PlegmaColors.textDim, height: 1.55),
                ),
                const SizedBox(height: 10),
                Row(children: [
                  const Icon(Icons.dns_outlined,
                      size: 12, color: PlegmaColors.textDim),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      'Servidor: $_servidorAtual',
                      style: const TextStyle(
                          fontSize: 10, color: PlegmaColors.textDim),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ]),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Grid 3×4 de entrada ─────────────────────────────────────────────
          GridView.builder(
            shrinkWrap: true,
            physics   : const NeverScrollableScrollPhysics(),
            itemCount : 12,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount  : 3,
              childAspectRatio: 2.4,
              crossAxisSpacing: 8,
              mainAxisSpacing : 8,
            ),
            itemBuilder: (_, i) => Container(
              decoration: BoxDecoration(
                color       : PlegmaColors.bg2,
                borderRadius: BorderRadius.circular(8),
                border      : Border.all(color: PlegmaColors.border),
              ),
              child: Row(
                children: [
                  SizedBox(
                    width: 22,
                    child: Center(
                      child: Text('${i + 1}',
                          style: const TextStyle(
                              fontSize: 9, color: PlegmaColors.textDim)),
                    ),
                  ),
                  Expanded(
                    child: TextField(
                      controller       : _ctrl[i],
                      focusNode        : _focus[i],
                      style            : const TextStyle(
                          fontSize: 12, color: PlegmaColors.text),
                      decoration       : const InputDecoration(
                        border        : InputBorder.none,
                        contentPadding: EdgeInsets.symmetric(
                            horizontal: 4, vertical: 8),
                        isDense: true,
                      ),
                      textInputAction: i < 11
                          ? TextInputAction.next
                          : TextInputAction.done,
                      autocorrect        : false,
                      enableSuggestions  : false,
                      textCapitalization : TextCapitalization.none,
                      onSubmitted        : (_) {
                        if (i < 11) _focus[i + 1].requestFocus();
                        else FocusScope.of(context).unfocus();
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // ── Erro ────────────────────────────────────────────────────────────
          if (_erro != null) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color       : PlegmaColors.red.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border      : Border.all(
                    color: PlegmaColors.red.withValues(alpha: 0.4)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.error_outline,
                      color: PlegmaColors.red, size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(_erro!,
                        style: const TextStyle(
                            fontSize: 11, color: PlegmaColors.red, height: 1.4)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── Resultado encontrado ─────────────────────────────────────────────
          if (_encontrado && _plgAddress != null) ...[
            PlegmaCard(
              borderColor: PlegmaColors.green.withValues(alpha: 0.45),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(children: [
                    Icon(Icons.check_circle_outline,
                        color: PlegmaColors.green, size: 18),
                    SizedBox(width: 8),
                    Text('Carteira encontrada na rede PLEGMA',
                        style: TextStyle(
                            fontSize  : 12,
                            color     : PlegmaColors.green,
                            fontWeight: FontWeight.bold)),
                  ]),
                  const SizedBox(height: 14),

                  const Text('ENDEREÇO PLG',
                      style: TextStyle(
                          fontSize    : 9,
                          color       : PlegmaColors.textDim,
                          letterSpacing: 2)),
                  const SizedBox(height: 4),
                  Row(children: [
                    Expanded(
                      child: Text(_plgAddress!,
                          style: const TextStyle(
                              fontSize     : 11,
                              color        : PlegmaColors.cyan,
                              letterSpacing: 0.5)),
                    ),
                    GestureDetector(
                      onTap: _copiarEndereco,
                      child: const Padding(
                        padding: EdgeInsets.only(left: 8),
                        child: Icon(Icons.copy,
                            size: 15, color: PlegmaColors.textDim),
                      ),
                    ),
                  ]),

                  if (_anchorId != null) ...[
                    const SizedBox(height: 10),
                    const Text('ÂNCORA ZK',
                        style: TextStyle(
                            fontSize    : 9,
                            color       : PlegmaColors.textDim,
                            letterSpacing: 2)),
                    const SizedBox(height: 4),
                    Text(_anchorId!,
                        style: const TextStyle(
                            fontSize: 10, color: PlegmaColors.textDim),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis),
                  ],

                  if (_createdAt != null) ...[
                    const SizedBox(height: 10),
                    Text(
                      'Registrado: ${DateTime.fromMillisecondsSinceEpoch(_createdAt! * 1000).toLocal().toString().substring(0, 16)}',
                      style: const TextStyle(
                          fontSize: 10, color: PlegmaColors.textDim),
                    ),
                  ],

                  const SizedBox(height: 16),
                  const Divider(color: PlegmaColors.border, height: 1),
                  const SizedBox(height: 14),

                  Text(
                    _semChaves
                        ? 'Endereço encontrado. As chaves criptográficas não estão '
                          'neste backup — a carteira será restaurada em modo leitura '
                          '(saldo visível, transações indisponíveis).'
                        : 'Identidade confirmada. Seed phrase, endereço e chaves '
                          'serão totalmente restaurados neste dispositivo.',
                    style: TextStyle(
                        fontSize  : 11,
                        color     : _semChaves ? PlegmaColors.amber : PlegmaColors.textDim,
                        height    : 1.6),
                  ),
                  const SizedBox(height: 16),

                  // ── Botão ENTRAR ────────────────────────────────────────────
                  SizedBox(
                    width : double.infinity,
                    height: 48,
                    child : ElevatedButton.icon(
                      onPressed: _restaurando ? null : _restaurarConta,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: PlegmaColors.green,
                        foregroundColor: Colors.black,
                      ),
                      icon : _restaurando
                          ? const SizedBox(
                              width: 16, height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.black))
                          : const Icon(Icons.login, size: 18),
                      label: Text(_restaurando
                          ? 'RESTAURANDO...'
                          : 'ENTRAR NO PLEGMA'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
          ],

          // ── Botão verificar ──────────────────────────────────────────────────
          if (!_encontrado)
            SizedBox(
              width : double.infinity,
              height: 48,
              child : ElevatedButton.icon(
                onPressed: _consultando ? null : _consultar,
                icon : _consultando
                    ? const SizedBox(
                        width: 16, height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: PlegmaColors.bg))
                    : const Icon(Icons.travel_explore, size: 18),
                label: Text(_consultando
                    ? 'CONSULTANDO REDE...'
                    : 'VERIFICAR SEED PHRASE'),
              ),
            ),

        ],
      ),
    );
  }
}
