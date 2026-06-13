import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/wallet_provider.dart';
import '../../services/api_service.dart';
import '../../services/deep_link_service.dart';
import '../../theme/plegma_theme.dart' show PlegmaColors;

/// Ecrã de confirmação de pagamento PLG para o Plegma Timestamp.
/// Aberto como modal quando o utilizador escaneia o QR de ancoragem.
class PayScreen extends StatefulWidget {
  final PaymentRequest payment;
  const PayScreen({super.key, required this.payment});

  @override
  State<PayScreen> createState() => _PayScreenState();
}

class _PayScreenState extends State<PayScreen> {
  _Status _status = _Status.idle;
  String? _txHash;
  String? _erro;
  String? _certificateUrl;

  PaymentRequest get _pay => widget.payment;

  Future<void> _confirmar() async {
    setState(() { _status = _Status.loading; _erro = null; });

    final wallet = context.read<WalletProvider>();

    // 1. Verificar saldo disponível
    final disponivel = wallet.wallet?.disponivel ?? 0;
    if (disponivel < _pay.amount) {
      setState(() {
        _status = _Status.erro;
        _erro = 'Saldo insuficiente: ${disponivel.toStringAsFixed(2)} PLG disponível '
                '(necessário: ${_pay.amount} PLG)';
      });
      return;
    }

    // 2. Executar transferência PLG
    final result = await wallet.transferir(
      destinatario: _pay.to,
      amount      : _pay.amount,
    );

    if (result == null || result['erro'] != null) {
      setState(() {
        _status = _Status.erro;
        _erro   = result?['erro'] as String? ?? 'Transferência falhou. Tente novamente.';
      });
      return;
    }

    final txHash = result['tx_hash'] as String? ?? '';
    if (txHash.isEmpty) {
      setState(() { _status = _Status.erro; _erro = 'TX hash não recebido.'; });
      return;
    }

    _txHash = txHash;
    setState(() { _status = _Status.confirmando; });

    // 3. Notificar o Plegma Timestamp via callback URL
    final fromWallet = wallet.wallet?.plgAddress ?? '';
    final ok = await ApiService.confirmTimestampPayment(
      callbackUrl : _pay.callbackUrl,
      sessionId   : _pay.sessionId,
      plgTxHash   : txHash,
      fromWallet  : fromWallet,
      amount      : _pay.amount,
    );

    if (!ok) {
      // Pagamento confirmado on-chain mas callback falhou
      // O Timestamp detectará o pagamento pelo polling da sessão
      setState(() {
        _status      = _Status.sucesso;
        _erro        = 'Pagamento confirmado. O certificado estará disponível em breve '
                       '(callback temporariamente indisponível).';
      });
      return;
    }

    // 4. Aguardar resposta do Timestamp (polling por 20s)
    String? certId;
    for (int i = 0; i < 10; i++) {
      await Future.delayed(const Duration(seconds: 2));
      final status = await ApiService.get(
        '${_pay.callbackUrl.replaceFirst('/api/payment/confirm', '')}'
        '/api/payment/status/${_pay.sessionId}',
      );
      if (status?['status'] == 'anchored') {
        certId = status?['certificate_id'] as String?;
        break;
      }
    }

    // Limpa o pedido pendente
    DeepLinkService.pendingPayment.value = null;

    setState(() {
      _status         = _Status.sucesso;
      _certificateUrl = certId != null
          ? '${_pay.callbackUrl.replaceFirst('/api/payment/confirm', '')}'
            '/api/certificate/$certId'
          : null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final c  = PlegmaColors.cyan;
    final bg = PlegmaColors.bg3;

    return Container(
      decoration: BoxDecoration(
        color       : bg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: EdgeInsets.fromLTRB(
        24, 16, 24, MediaQuery.of(context).viewInsets.bottom + 32,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Handle
          Center(
            child: Container(
              width: 40, height: 4,
              margin: const EdgeInsets.only(bottom: 20),
              decoration: BoxDecoration(
                color       : Colors.white24,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),

          if (_status == _Status.idle || _status == _Status.loading) ..._buildConfirm(c),
          if (_status == _Status.confirmando)               ..._buildConfirmando(c),
          if (_status == _Status.sucesso)                   ..._buildSucesso(c),
          if (_status == _Status.erro)                      ..._buildErro(),
        ],
      ),
    );
  }

  // ── Estados da UI ─────────────────────────────────────────────────────────

  List<Widget> _buildConfirm(Color c) => [
    Row(children: [
      Icon(Icons.lock_outline_rounded, color: c, size: 22),
      const SizedBox(width: 10),
      Text('Plegma Timestamp', style: TextStyle(color: c, fontSize: 16, fontWeight: FontWeight.bold)),
    ]),
    const SizedBox(height: 6),
    Text('Ancoragem criptográfica de documento', style: TextStyle(color: Colors.white54, fontSize: 13)),
    const SizedBox(height: 24),

    // Detalhe da transação
    _DetailRow(label: 'Valor',      value: '${_pay.amount.toStringAsFixed(0)} PLG'),
    _DetailRow(label: 'Destino',    value: '${_pay.to.substring(0, 12)}…${_pay.to.substring(_pay.to.length - 6)}'),
    if (_pay.ref.isNotEmpty)
      _DetailRow(label: 'Doc (hash)', value: '${_pay.ref.substring(0, 16)}…', mono: true),
    const SizedBox(height: 24),

    // Botões
    SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: _status == _Status.loading ? null : _confirmar,
        style: ElevatedButton.styleFrom(
          backgroundColor: c,
          foregroundColor: Colors.black,
          padding        : const EdgeInsets.symmetric(vertical: 16),
          shape          : RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
        child: _status == _Status.loading
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
            : const Text('Confirmar Pagamento', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
      ),
    ),
    const SizedBox(height: 10),
    SizedBox(
      width: double.infinity,
      child: TextButton(
        onPressed: () { DeepLinkService.pendingPayment.value = null; Navigator.pop(context); },
        child: const Text('Cancelar', style: TextStyle(color: Colors.white54)),
      ),
    ),
  ];

  List<Widget> _buildConfirmando(Color c) => [
    const Center(child: CircularProgressIndicator()),
    const SizedBox(height: 20),
    Center(child: Text('A ancorar na rede PLEGMA…', style: TextStyle(color: c, fontSize: 15))),
    const SizedBox(height: 8),
    Center(child: Text('TX: ${_txHash?.substring(0, 20) ?? '—'}…', style: const TextStyle(color: Colors.white38, fontSize: 12, fontFamily: 'monospace'))),
    const SizedBox(height: 24),
  ];

  List<Widget> _buildSucesso(Color c) => [
    Row(children: [
      Icon(Icons.check_circle_outline, color: c, size: 28),
      const SizedBox(width: 10),
      Text('Documento ancorado!', style: TextStyle(color: c, fontSize: 17, fontWeight: FontWeight.bold)),
    ]),
    const SizedBox(height: 12),
    if (_txHash != null) ...[
      _DetailRow(label: 'TX Hash', value: '${_txHash!.substring(0, 20)}…', mono: true),
    ],
    if (_erro != null) ...[
      const SizedBox(height: 8),
      Text(_erro!, style: const TextStyle(color: Colors.amber, fontSize: 12)),
    ],
    const SizedBox(height: 20),
    if (_certificateUrl != null)
      SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          icon : const Icon(Icons.download_outlined, size: 18),
          label: const Text('Descarregar Certificado PDF'),
          style: ElevatedButton.styleFrom(
            backgroundColor: c,
            foregroundColor: Colors.black,
            padding        : const EdgeInsets.symmetric(vertical: 14),
            shape          : RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          ),
          onPressed: () {
            launchUrl(Uri.parse(_certificateUrl!), mode: LaunchMode.externalApplication);
          },
        ),
      ),
    const SizedBox(height: 10),
    SizedBox(
      width: double.infinity,
      child: TextButton(
        onPressed: () { Navigator.pop(context); },
        child: const Text('Fechar', style: TextStyle(color: Colors.white54)),
      ),
    ),
  ];

  List<Widget> _buildErro() => [
    const Row(children: [
      Icon(Icons.error_outline, color: Colors.redAccent, size: 26),
      SizedBox(width: 10),
      Text('Pagamento falhou', style: TextStyle(color: Colors.redAccent, fontSize: 16, fontWeight: FontWeight.bold)),
    ]),
    const SizedBox(height: 12),
    Text(_erro ?? 'Erro desconhecido.', style: const TextStyle(color: Colors.white70, fontSize: 13)),
    const SizedBox(height: 20),
    SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: () => setState(() { _status = _Status.idle; _erro = null; }),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.redAccent,
          foregroundColor: Colors.white,
          padding        : const EdgeInsets.symmetric(vertical: 14),
          shape          : RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
        child: const Text('Tentar Novamente'),
      ),
    ),
    const SizedBox(height: 10),
    SizedBox(
      width: double.infinity,
      child: TextButton(
        onPressed: () { DeepLinkService.pendingPayment.value = null; Navigator.pop(context); },
        child: const Text('Cancelar', style: TextStyle(color: Colors.white38)),
      ),
    ),
  ];
}

enum _Status { idle, loading, confirmando, sucesso, erro }

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;
  final bool   mono;
  const _DetailRow({required this.label, required this.value, this.mono = false});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child  : Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 13)),
        Text(
          value,
          style: TextStyle(
            color     : Colors.white,
            fontSize  : 13,
            fontFamily: mono ? 'monospace' : null,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    ),
  );
}
