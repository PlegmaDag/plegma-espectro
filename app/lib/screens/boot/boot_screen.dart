import 'package:flutter/material.dart';
import '../../services/crypto_service.dart';
import '../../services/storage_service.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../services/seed_service.dart';
import '../../theme/plegma_theme.dart';
import '../auth/seed_phrase_screen.dart';
import '../auth/recover_account_screen.dart';

// ============================================================================
// BOOT SCREEN — Primeiro boot
// Fases: verificar carteira → gerar chave → home
// O servidor é conectado automaticamente (default hardcoded em ApiService).
// Override de IP disponível no Drawer → item DEV.
// ============================================================================

class BootScreen extends StatefulWidget {
  const BootScreen({super.key});

  @override
  State<BootScreen> createState() => _BootScreenState();
}

class _BootScreenState extends State<BootScreen>
    with SingleTickerProviderStateMixin {

  late AnimationController _pulseCtrl;
  late Animation<double>   _pulseAnim;

  bool   _verificando    = true;
  bool   _mostrarOpcoes  = false;   // escolha: nova carteira / recuperar
  bool   _gerandoChave   = false;
  bool   _erroFatal      = false;
  String _fase           = 'Verificando carteira...';
  String _erroMsg        = '';
  double _progresso      = 0;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync   : this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.3, end: 1.0).animate(_pulseCtrl);

    WidgetsBinding.instance.addPostFrameCallback((_) => _verificar());
  }

  Future<void> _verificar() async {
    await Future.delayed(const Duration(milliseconds: 600));

    // Migração única: move dados salvos com encryptedSharedPreferences=true
    // (APKs antigos) para o backend Keystore directo (encryptedSharedPreferences=false).
    try { await StorageService.migrarStorageLegado(); } catch (_) {}

    bool temCarteira = false;
    try {
      temCarteira = await StorageService.carteiraConfigurada()
          .timeout(const Duration(seconds: 8));
    } catch (e) { debugPrint('Erro: $e'); }

    if (temCarteira) {
      // Já configurado — restaura host salvo (pode ser override de dev) e vai para home
      try {
        final host = await StorageService.lerHost()
            .timeout(const Duration(seconds: 5));
        ApiService.setHost(host);
      } catch (e) { debugPrint('Erro: $e'); }

      // Auto-registo na rede: heartbeat com PLG address no metadata é suficiente
      // em fase pré-launch (network_phase.py — plg_valido path, sem assinatura obrigatória).
      // Garante entrada em nos_rede mesmo quando seed backup falhou no primeiro boot.
      try {
        final addr = await StorageService.lerEndereco();
        if (addr != null && addr.isNotEmpty) {
          await ApiService.nodeHeartbeat(
            'WALLET_$addr',
            publicKey: '',
            signature: '',
            metadata : {'node_type': 'WALLET', 'plg_address': addr},
          );
          // Tenta seed backup adicionalmente se as palavras estiverem disponíveis
          final backed = await SeedService.backupFeito();
          if (!backed) {
            final words = await SeedService.ler();
            if (words != null) {
              await SeedService.enviarZkBackup(plgAddress: addr, words: words);
            }
          }
        }
      } catch (_) {}

      // Bloqueia imediatamente — HomeScreen exibirá LockScreen overlay
      AuthService.lock();
      if (mounted) Navigator.pushReplacementNamed(context, '/home');
    } else {
      // Nenhuma carteira — oferece escolha ao usuário
      setState(() { _verificando = false; _mostrarOpcoes = true; });
    }
  }

  Future<void> _gerarCarteira() async {
    final fases = [
      ('Iniciando ambiente seguro...', 0.15),
      ('Coletando entropia do hardware...', 0.30),
      ('Gerando par de chaves Dilithium3...', 0.55),
      ('Vinculando identidade ao dispositivo...', 0.75),
      ('Finalizando...', 0.90),
    ];

    for (final (label, prog) in fases) {
      setState(() { _fase = label; _progresso = prog; });
      await Future.delayed(const Duration(milliseconds: 700));
    }

    late KeyPair kp;
    try {
      kp = await CryptoService.gerarCarteira();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erroFatal    = true;
        _erroMsg      = e.toString();
        _gerandoChave = false;
        _progresso    = 0;
      });
      return;
    }

    try {
      await StorageService.salvarChavePrivada(kp.privateKey);
      await StorageService.salvarChavePublica(kp.publicKey);
      await StorageService.salvarEndereco(kp.address);
      await StorageService.salvarHost(ApiService.defaultHost);
      await StorageService.marcarOnboardingCompleto();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erroFatal    = true;
        _erroMsg      = 'Erro ao salvar carteira no dispositivo: ${e.toString()}';
        _gerandoChave = false;
        _progresso    = 0;
      });
      return;
    }

    // Gera frase de recuperação (12 palavras) para o primeiro boot
    List<String> seedWords;
    try {
      seedWords = await SeedService.gerar();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erroFatal    = true;
        _erroMsg      = 'Erro ao gerar frase de recuperação: ${e.toString()}';
        _gerandoChave = false;
        _progresso    = 0;
      });
      return;
    }

    setState(() {
      _progresso    = 1.0;
      _fase         = 'Gerando frase de recuperação...';
      _gerandoChave = false;
    });

    await Future.delayed(const Duration(milliseconds: 600));

    // Navega para tela de exibição/confirmação da seed phrase
    if (mounted) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => SeedPhraseScreen(
            words     : seedWords,
            plgAddress: kp.address,
          ),
        ),
      );
    }
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [

              AnimatedBuilder(
                animation: _pulseAnim,
                builder : (_, __) => Opacity(
                  opacity: _pulseAnim.value,
                  child: Image.asset('assets/images/logo.png', width: 100, height: 100),
                ),
              ),

              const SizedBox(height: 16),

              const Text('PLEGMA', style: TextStyle(
                fontSize: 28, fontWeight: FontWeight.bold,
                color: PlegmaColors.cyan, letterSpacing: 8,
              )),

              const SizedBox(height: 4),

              const Text('Soberania Digital', style: TextStyle(
                fontSize: 12, color: PlegmaColors.textDim, letterSpacing: 4,
              )),

              const SizedBox(height: 48),

              // ── Erro fatal ──
              if (_erroFatal) ...[
                Container(
                  padding   : const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color       : PlegmaColors.bg2,
                    borderRadius: BorderRadius.circular(12),
                    border      : Border.all(color: Colors.redAccent.withOpacity(0.5)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(children: [
                        Icon(Icons.error_outline, color: Colors.redAccent, size: 18),
                        SizedBox(width: 8),
                        Text('ERRO AO INICIAR', style: TextStyle(
                          fontSize: 11, color: Colors.redAccent,
                          letterSpacing: 2, fontWeight: FontWeight.bold,
                        )),
                      ]),
                      const SizedBox(height: 12),
                      Text(_erroMsg, style: const TextStyle(
                          fontSize: 11, color: PlegmaColors.textDim, height: 1.5)),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: () {
                      setState(() {
                        _erroFatal    = false;
                        _gerandoChave = true;
                        _progresso    = 0;
                        _fase         = 'Iniciando ambiente seguro...';
                      });
                      _gerarCarteira();
                    },
                    icon : const Icon(Icons.refresh, size: 18),
                    label: const Text('TENTAR NOVAMENTE'),
                  ),
                ),
              ],

              // ── Verificando ──
              if (_verificando)
                const CircularProgressIndicator(color: PlegmaColors.cyan, strokeWidth: 2),

              // ── Escolha: nova carteira ou recuperar ──
              if (_mostrarOpcoes) ...[
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton.icon(
                    onPressed: () {
                      setState(() { _mostrarOpcoes = false; _gerandoChave = true; });
                      _gerarCarteira();
                    },
                    icon : const Icon(Icons.add_circle_outline, size: 20),
                    label: const Text('CRIAR NOVA CARTEIRA',
                        style: TextStyle(letterSpacing: 1.5)),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const RecoverAccountScreen()),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: PlegmaColors.amber),
                      foregroundColor: PlegmaColors.amber,
                    ),
                    icon : const Icon(Icons.restore, size: 20,
                        color: PlegmaColors.amber),
                    label: const Text('RECUPERAR CONTA',
                        style: TextStyle(
                            letterSpacing: 1.5, color: PlegmaColors.amber)),
                  ),
                ),
              ],

              // ── Gerando chave / conectando ──
              if (_gerandoChave || (_progresso == 1.0 && !_erroFatal)) ...[
                Text(_fase, style: const TextStyle(
                    fontSize: 13, color: PlegmaColors.text3, letterSpacing: 1),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value          : _progresso,
                    backgroundColor: PlegmaColors.bg3,
                    color          : PlegmaColors.cyan,
                    minHeight      : 4,
                  ),
                ),
                const SizedBox(height: 12),
                Text('${(_progresso * 100).toInt()}%',
                  style: const TextStyle(
                      fontSize: 12, color: PlegmaColors.cyan, letterSpacing: 2),
                ),
              ],

            ],
          ),
        ),
      ),
    );
  }
}
