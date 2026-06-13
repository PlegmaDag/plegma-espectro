import 'package:flutter/foundation.dart';

/// Pedido de pagamento recebido via deep link plegma://pay
class PaymentRequest {
  final String to;
  final double amount;
  final String asset;
  final String ref;         // hash do documento
  final String sessionId;
  final String callbackUrl;

  const PaymentRequest({
    required this.to,
    required this.amount,
    required this.asset,
    required this.ref,
    required this.sessionId,
    required this.callbackUrl,
  });
}

/// Serviço de deep links — mantém nonces e pedidos de pagamento pendentes.
///
/// Fluxo auth:
///   1. main.dart recebe URI plegma://auth?nonce=XXX via app_links
///   2. Define DeepLinkService.pendingAuthNonce.value = nonce
///   3. HomeScreen ouve → muda para aba Shield (índice 3)
///   4. ShieldScreen ouve → chama _processarQR automaticamente
///
/// Fluxo pagamento (Plegma Timestamp):
///   1. main.dart recebe URI plegma://pay?to=PLG...&amount=2&asset=PLG&ref=...&session=...&cb=...
///   2. Define DeepLinkService.pendingPayment.value = PaymentRequest
///   3. HomeScreen ouve → mostra PayScreen como modal
///   4. PayScreen executa transferência + chama callback URL
class DeepLinkService {
  DeepLinkService._();

  /// Nonce de autenticação Shield recebido via deep link.
  static final pendingAuthNonce = ValueNotifier<String?>(null);

  /// Nonce de autenticação do Console Mestre (role=admin).
  static final pendingAdminNonce = ValueNotifier<String?>(null);

  /// Pedido de pagamento PLG recebido via deep link.
  static final pendingPayment = ValueNotifier<PaymentRequest?>(null);

  // Caracteres que permitem HTML/CRLF/null-byte injection.
  static final _nonceUnsafe = RegExp('[<>&"\'\r\n\x00]');

  /// Processa uma URI recebida via deep link.
  static void handleUri(Uri uri) {
    if (uri.scheme != 'plegma') return;

    switch (uri.host) {
      case 'auth':
        final nonce = uri.queryParameters['nonce'];
        final role  = uri.queryParameters['role'] ?? '';
        if (nonce != null && nonce.isNotEmpty && !_nonceUnsafe.hasMatch(nonce)) {
          if (role == 'admin') {
            pendingAdminNonce.value = nonce;
          } else {
            pendingAuthNonce.value = nonce;
          }
        }
        break;

      case 'pay':
        final to       = uri.queryParameters['to']      ?? '';
        final amountS  = uri.queryParameters['amount']  ?? '0';
        final asset    = uri.queryParameters['asset']   ?? 'PLG';
        final ref      = uri.queryParameters['ref']     ?? '';
        final session  = uri.queryParameters['session'] ?? '';
        final cb       = uri.queryParameters['cb']      ?? '';

        final amount = double.tryParse(amountS) ?? 0;

        // Validações mínimas de segurança
        if (to.startsWith('PLG') && to.length >= 20 &&
            amount > 0 && amount <= 1000 &&
            asset == 'PLG' &&
            session.isNotEmpty && !_nonceUnsafe.hasMatch(session) &&
            cb.startsWith('https://')) {
          pendingPayment.value = PaymentRequest(
            to         : to,
            amount     : amount,
            asset      : asset,
            ref        : ref,
            sessionId  : session,
            callbackUrl: cb,
          );
        }
        break;

      // plegma://prover → tratado pelo ProversScreen separadamente
    }
  }
}
