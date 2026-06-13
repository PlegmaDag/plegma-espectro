import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../theme/plegma_theme.dart';
import '../../providers/wallet_provider.dart';
import '../../providers/validator_provider.dart';
import '../../services/deep_link_service.dart';
import '../../services/api_service.dart';
import '../../services/storage_service.dart';
import '../../services/auth_service.dart';
import '../../services/heartbeat_service.dart';
import '../../services/crypto_service.dart';
import '../../services/dilithium_ffi_service.dart';
import '../auth/lock_screen.dart';
import '../wallet/wallet_screen.dart';
import '../sentinela/sentinela_screen.dart';
import '../shield/shield_screen.dart';
import '../governanca/governanca_screen.dart';
import '../timestamp/pay_screen.dart';
import 'home_dashboard.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  int _tab = 0;
  late final List<Widget> _screens;
  Timer? _adminPollTimer;
  bool _adminDialogAberto = false;

  @override
  void initState() {
    super.initState();
    _screens = [const HomeDashboard(), const WalletScreen(), const SentinelaScreen(), const ShieldScreen(), const GovernancaScreen()];
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      context.read<WalletProvider>().inicializar();
      context.read<ValidatorProvider>().inicializar();
      HeartbeatService.instance.start();
    });
    DeepLinkService.pendingAuthNonce.addListener(_onDeepLinkAuth);
    DeepLinkService.pendingAdminNonce.addListener(_onDeepLinkAdmin);
    DeepLinkService.pendingPayment.addListener(_onDeepLinkPayment);
    // Pollar servidor a cada 5s para aprovações admin pendentes
    _adminPollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _checkPendingAdminAuth());
  }

  @override
  void dispose() {
    _adminPollTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    DeepLinkService.pendingAuthNonce.removeListener(_onDeepLinkAuth);
    DeepLinkService.pendingAdminNonce.removeListener(_onDeepLinkAdmin);
    DeepLinkService.pendingPayment.removeListener(_onDeepLinkPayment);
    super.dispose();
  }

  Future<void> _checkPendingAdminAuth() async {
    if (!mounted || _adminDialogAberto) return;
    try {
      final result = await ApiService.adminAuthPending();
      final nonce = result?['nonce'] as String?;
      if (result?['pending'] == true && nonce != null && mounted) {
        _adminDialogAberto = true;
        await _mostrarDialogoAdminAuth(nonce);
        _adminDialogAberto = false;
      }
    } catch (_) {}
  }

  // ── Lifecycle: bloqueia ao ir para background ─────────────────────────────
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Bloqueia apenas em paused (app vai para background real).
    // inactive dispara em qualquer dialog do sistema e causaria lock constante.
    if (state == AppLifecycleState.paused) {
      if (AuthService.canLock) AuthService.lock();
    } else if (state == AppLifecycleState.resumed) {
      AuthService.markResumed();
    }
  }

  void _onDeepLinkAuth() {
    if (DeepLinkService.pendingAuthNonce.value != null && !kIsWeb) {
      setState(() => _tab = 3); // Shield — apenas Android
    }
  }

  void _onDeepLinkAdmin() {
    final nonce = DeepLinkService.pendingAdminNonce.value;
    if (nonce != null && mounted) {
      DeepLinkService.pendingAdminNonce.value = null;
      _mostrarDialogoAdminAuth(nonce);
    }
  }

  void _onDeepLinkPayment() {
    final payment = DeepLinkService.pendingPayment.value;
    if (payment == null || !mounted) return;
    showModalBottomSheet(
      context           : context,
      isScrollControlled: true,
      backgroundColor  : Colors.transparent,
      builder           : (_) => PayScreen(payment: payment),
    );
  }

  Future<void> _mostrarDialogoAdminAuth(String nonce) async {
    String status = 'Confirmar autenticação do Console Mestre?';
    bool processando = false;

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          backgroundColor: const Color(0xFF0d0d14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: Colors.cyan.withValues(alpha: 0.3)),
          ),
          title: const Text('⬡ Console Mestre',
              style: TextStyle(color: Color(0xFF00f2ff), fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(status, style: const TextStyle(color: Color(0xFFb0b0c0))),
              const SizedBox(height: 8),
              Text('Nonce: ${nonce.substring(0, 16)}…',
                  style: const TextStyle(color: Color(0xFF606080), fontSize: 11)),
            ],
          ),
          actions: processando
              ? [const Padding(
                  padding: EdgeInsets.all(12),
                  child: SizedBox(width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00f2ff))),
                )]
              : [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('Cancelar', style: TextStyle(color: Color(0xFF606080))),
                  ),
                  ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF00f2ff),
                      foregroundColor: const Color(0xFF0d0d14),
                    ),
                    onPressed: () async {
                      setS(() { processando = true; status = 'Verificando biometria…'; });

                      AuthService.beginExternalAuth();
                      final autorizado = await AuthService.authenticateBiometric(
                        reason: 'Autorizar acesso ao Console Mestre PLEGMA',
                      );
                      if (!autorizado) {
                        setS(() { processando = false; status = '✗ Biometria não confirmada'; });
                        return;
                      }

                      setS(() => status = 'Assinando com Dilithium3…');
                      final privKey = await StorageService.lerChavePrivada() ?? '';
                      final pubKey  = await StorageService.lerChavePublica() ?? '';
                      final addr    = await StorageService.lerEndereco() ?? '';

                      if (privKey.isEmpty || pubKey.isEmpty || addr.isEmpty) {
                        setS(() { processando = false; status = '✗ Carteira não encontrada'; });
                        return;
                      }

                      String sigHex, pubHex;
                      try {
                        final sigB64 = await CryptoService.assinarNonce(nonce, privKey);
                        sigHex = DilithiumFfiService.bytesToHex(base64.decode(sigB64));
                        pubHex = DilithiumFfiService.bytesToHex(base64.decode(pubKey));
                      } catch (_) {
                        setS(() { processando = false; status = '✗ Erro FFI — motor criptográfico indisponível'; });
                        return;
                      }

                      setS(() => status = 'Verificando no servidor…');
                      final result = await ApiService.adminAuthVerify(
                        nonce      : nonce,
                        plgAddress : addr,
                        signature  : sigHex,
                        publicKey  : pubHex,
                      );

                      final ok = result?['status'] == 'autenticado' || result?['token'] != null;
                      if (ok) {
                        setS(() { processando = false; status = '✓ Acesso concedido!'; });
                        await Future.delayed(const Duration(seconds: 1));
                        if (ctx.mounted) Navigator.pop(ctx);
                      } else {
                        final err = result?['erro'] ?? result?['error'] ?? 'Servidor indisponível';
                        setS(() { processando = false; status = '✗ $err'; });
                      }
                    },
                    child: const Text('Autenticar'),
                  ),
                ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: AuthService.lockedNotifier,
      builder: (_, locked, child) => Stack(
        children: [
          child!,
          if (locked) const LockScreen(),
        ],
      ),
      child: _buildHome(context),
    );
  }

  Widget _buildHome(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      drawer: _buildDrawer(context),
      body: IndexedStack(index: _tab, children: _screens),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: PlegmaColors.border, width: 1)),
        ),
        child: BottomNavigationBar(
          currentIndex: _tab,
          onTap       : (i) => setState(() => _tab = i),
          type        : BottomNavigationBarType.fixed,
          items       : const [
                  BottomNavigationBarItem(icon: Icon(Icons.hub_outlined),                    activeIcon: Icon(Icons.hub),                    label: 'REDE'),
                  BottomNavigationBarItem(icon: Icon(Icons.account_balance_wallet_outlined), activeIcon: Icon(Icons.account_balance_wallet), label: 'WALLET'),
                  BottomNavigationBarItem(icon: Icon(Icons.security_outlined),               activeIcon: Icon(Icons.security),               label: 'SENTINELA'),
                  BottomNavigationBarItem(icon: Icon(Icons.shield_outlined),                 activeIcon: Icon(Icons.shield),                 label: 'SHIELD'),
                  BottomNavigationBarItem(icon: Icon(Icons.how_to_vote_outlined),            activeIcon: Icon(Icons.how_to_vote),            label: 'GOVERN.'),
                ],
        ),
      ),
    );
  }

  void _mostrarDialogServidor(BuildContext context) {
    final ctrl = TextEditingController(text: ApiService.baseUrl.replaceAll('http://', '').split(':')[0]);
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: PlegmaColors.bg2,
        title: const Text('Servidor', style: TextStyle(
            color: PlegmaColors.cyan, fontSize: 13, letterSpacing: 2)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('IP ou hostname do nó PLEGMA',
                style: TextStyle(fontSize: 11, color: PlegmaColors.textDim)),
            const SizedBox(height: 8),
            TextField(
              controller  : ctrl,
              style       : const TextStyle(color: PlegmaColors.cyan, fontSize: 13),
              decoration  : const InputDecoration(
                hintText  : 'api.plegmadag.com',
                prefixIcon: Icon(Icons.dns_outlined, color: PlegmaColors.textDim, size: 18),
              ),
              keyboardType: TextInputType.url,
              autofocus   : true,
            ),
            const SizedBox(height: 8),
            Text('Padrão: ${ApiService.defaultHost}',
                style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCELAR', style: TextStyle(color: PlegmaColors.textDim)),
          ),
          TextButton(
            onPressed: () async {
              final host = ctrl.text.trim();
              if (host.isEmpty) return;
              ApiService.setHost(host);
              await StorageService.salvarHost(host);
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('SALVAR', style: TextStyle(color: PlegmaColors.cyan)),
          ),
        ],
      ),
    );
  }

  Widget _buildDrawer(BuildContext context) {
    final nos = context.watch<ValidatorProvider>().nosAtivos;
    return Drawer(
      backgroundColor: PlegmaColors.bg2,
      child: SafeArea(
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              child: Row(children: const [
                Text('⬡', style: TextStyle(fontSize: 24, color: PlegmaColors.cyan)),
                SizedBox(width: 12),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('PLEGMA DAG', style: TextStyle(fontSize: 14, color: PlegmaColors.cyan, fontWeight: FontWeight.bold, letterSpacing: 2)),
                  Text('V1.0 · Crystals-Dilithium3', style: TextStyle(fontSize: 10, color: PlegmaColors.textDim, letterSpacing: 1)),
                ]),
              ]),
            ),
            const Divider(color: PlegmaColors.border),
            ListTile(
              leading: const Icon(Icons.how_to_vote_outlined, color: PlegmaColors.amber),
              title  : const Text('GOVERNANÇA', style: TextStyle(color: PlegmaColors.amber, fontSize: 12, letterSpacing: 2)),
              subtitle: Text(nos < 10000 ? '$nos / 10.000 nós' : 'Quórum atingido',
                style: const TextStyle(fontSize: 10, color: PlegmaColors.textDim)),
              onTap: () {
                Navigator.pop(context);
                setState(() => _tab = 4);
              },
            ),
            const Spacer(),
            const Divider(color: PlegmaColors.border),
            // ── DEV: override de servidor ──────────────────────────
            ListTile(
              dense  : true,
              leading: const Icon(Icons.dns_outlined, color: PlegmaColors.textDim, size: 18),
              title  : const Text('Servidor', style: TextStyle(
                  color: PlegmaColors.textDim, fontSize: 11, letterSpacing: 1)),
              trailing: const Icon(Icons.edit_outlined, color: PlegmaColors.textDim, size: 16),
              onTap: () {
                Navigator.pop(context);
                _mostrarDialogServidor(context);
              },
            ),
            const Divider(color: PlegmaColors.border),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('© 2026 PLEGMA DAG\nTHE ARCHITECTURE OF ABSOLUTE JUSTICE',
                style: TextStyle(fontSize: 9, color: PlegmaColors.textDim, letterSpacing: 1, height: 1.6),
                textAlign: TextAlign.center),
            ),
          ],
        ),
      ),
    );
  }
}
