import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';
import 'package:app_links/app_links.dart';

import 'theme/plegma_theme.dart';
import 'providers/wallet_provider.dart';
import 'providers/validator_provider.dart';
import 'screens/auth/pattern_setup_screen.dart';
import 'screens/boot/boot_screen.dart';
import 'screens/home/home_screen.dart';
import 'l10n/app_localizations.dart';
import 'services/deep_link_service.dart';
import 'services/validator_bg_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor          : Colors.transparent,
    statusBarIconBrightness : Brightness.light,
  ));

  // Registra entrypoint do foreground service antes de runApp
  // Wrap em try-catch — falha não deve impedir o app de abrir
  try { await initValidatorBgService(); } catch (e) { debugPrint('Erro: $e'); }

  // Deep links — inicializa antes de runApp
  late final AppLinks appLinks;
  try {
    appLinks = AppLinks();
    // Cold start: app aberto diretamente via deep link
    final initialUri = await appLinks.getInitialLink();
    if (initialUri != null) {
      DeepLinkService.handleUri(initialUri);
    }
  } catch (_) {
    // Suprime erro fatal se a engine nativa falhar ao capturar a intent inicial
    appLinks = AppLinks();
  }

  runApp(PlegmaApp(appLinks: appLinks));
}

class PlegmaApp extends StatefulWidget {
  final AppLinks appLinks;
  const PlegmaApp({super.key, required this.appLinks});

  @override
  State<PlegmaApp> createState() => _PlegmaAppState();
}

class _PlegmaAppState extends State<PlegmaApp> {

  @override
  void initState() {
    super.initState();
    // Warm start: app já rodando, recebe deep link
    widget.appLinks.uriLinkStream.listen((uri) {
      DeepLinkService.handleUri(uri);
    });
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => WalletProvider()),
        ChangeNotifierProvider(create: (_) => ValidatorProvider()),
      ],
      child: MaterialApp(
        title                     : 'PLEGMA',
        debugShowCheckedModeBanner: false,
        theme                     : PlegmaTheme.dark(),

        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [
          Locale('pt', 'BR'), Locale('pt', 'PT'),
          Locale('en', ''),   Locale('es', ''),
          Locale('fr', ''),   Locale('de', ''),
          Locale('zh', ''),   Locale('ja', ''),
          Locale('ko', ''),   Locale('ar', ''),
          Locale('ru', ''),
        ],
        localeResolutionCallback: (locale, supported) {
          if (locale == null) return supported.first;
          for (final s in supported) {
            if (s.languageCode == locale.languageCode) return s;
          }
          return supported.first;
        },

        initialRoute: '/boot',
        routes: {
          '/boot'          : (_) => const BootScreen(),
          '/home'          : (_) => const HomeScreen(),
          '/pattern-setup' : (_) => const PatternSetupScreen(),
        },
      ),
    );
  }
}
