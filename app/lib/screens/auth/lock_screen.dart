import 'package:flutter/material.dart';
import '../../services/auth_service.dart';
import '../../theme/plegma_theme.dart';

// ============================================================================
// LOCK SCREEN — Autenticação por biometria do dispositivo (B1)
//
// B1 → biometria do sistema (digital / face ID / PIN do sistema)
//   Idêntica ao desbloqueio do celular.
//   Sucesso → AuthService.unlock()
//
// Nota: B2 (padrão de pontos anti-coação) está reservado para V2.0+.
// ============================================================================

class LockScreen extends StatefulWidget {
  const LockScreen({super.key});

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  bool _b1Running = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _triggerB1());
  }

  Future<void> _triggerB1() async {
    if (_b1Running) return;
    _b1Running = true;
    final ok = await AuthService.authenticateBiometric(
      reason: 'Desbloqueie o PLEGMA',
    );
    _b1Running = false;
    if (!mounted) return;
    if (ok) {
      AuthService.unlock();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PlegmaColors.bg,
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [

              Image.asset(
                'assets/images/logo.png',
                width : 80,
                height: 80,
              ),

              const SizedBox(height: 16),

              const Text(
                'PLEGMA',
                style: TextStyle(
                  fontSize     : 26,
                  fontWeight   : FontWeight.bold,
                  color        : PlegmaColors.cyan,
                  letterSpacing: 8,
                ),
              ),

              const SizedBox(height: 4),

              const Text(
                'Soberania Digital',
                style: TextStyle(
                  fontSize     : 11,
                  color        : PlegmaColors.textDim,
                  letterSpacing: 4,
                ),
              ),

              const SizedBox(height: 56),

              GestureDetector(
                onTap: _triggerB1,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 28, vertical: 14),
                  decoration: BoxDecoration(
                    border      : Border.all(color: PlegmaColors.cyanBord),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.fingerprint,
                          color: PlegmaColors.cyan, size: 22),
                      SizedBox(width: 10),
                      Text(
                        'AUTENTICAR',
                        style: TextStyle(
                          fontSize     : 12,
                          color        : PlegmaColors.cyan,
                          letterSpacing: 2,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

            ],
          ),
        ),
      ),
    );
  }
}
