import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// ============================================================================
// PLEGMA THEME — Identidade Visual
// Espelha o dashboard web: fundo escuro, ciano #00F2FF, Space Mono
// Adaptado para mobile: cards arredondados, gestos nativos
// ============================================================================

class PlegmaColors {
  static const Color bg       = Color(0xFF000000);
  static const Color bg2      = Color(0xFF050a14);
  static const Color bg3      = Color(0xFF0a1428);
  static const Color bg4      = Color(0xFF0d1f3c);

  static const Color cyan     = Color(0xFF00F2FF);
  static const Color cyanDim  = Color(0x2600F2FF);
  static const Color cyanBord = Color(0x4000F2FF);

  static const Color green    = Color(0xFF23d18b);
  static const Color amber    = Color(0xFFf59e0b);
  static const Color red      = Color(0xFFef4444);
  static const Color purple   = Color(0xFFa78bfa);

  static const Color text     = Color(0xFFe2e8f0);
  static const Color textDim  = Color(0xFF64748b);
  static const Color text3    = Color(0xFF94a3b8);

  static const Color border   = Color(0x2000F2FF);
  static const Color border2  = Color(0x4000F2FF);
}

class PlegmaTheme {
  static ThemeData dark() {
    final base = ThemeData.dark();
    return base.copyWith(
      scaffoldBackgroundColor: PlegmaColors.bg,
      colorScheme: const ColorScheme.dark(
        primary    : PlegmaColors.cyan,
        secondary  : PlegmaColors.green,
        surface    : PlegmaColors.bg2,
        error      : PlegmaColors.red,
      ),
      textTheme: GoogleFonts.jetBrainsMonoTextTheme(base.textTheme).apply(
        bodyColor     : PlegmaColors.text,
        displayColor  : PlegmaColors.cyan,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor   : PlegmaColors.bg2,
        foregroundColor   : PlegmaColors.cyan,
        elevation         : 0,
        centerTitle       : true,
        surfaceTintColor  : Colors.transparent,
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor      : PlegmaColors.bg2,
        selectedItemColor     : PlegmaColors.cyan,
        unselectedItemColor   : PlegmaColors.textDim,
        showSelectedLabels    : true,
        showUnselectedLabels  : true,
        type                  : BottomNavigationBarType.fixed,
        elevation             : 0,
      ),
      cardTheme: CardTheme(
        color        : PlegmaColors.bg2,
        elevation    : 0,
        shape        : RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side        : const BorderSide(color: PlegmaColors.border, width: 1),
        ),
        margin       : EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled          : true,
        fillColor       : PlegmaColors.bg3,
        border          : OutlineInputBorder(
          borderRadius  : BorderRadius.circular(8),
          borderSide    : const BorderSide(color: PlegmaColors.border),
        ),
        enabledBorder   : OutlineInputBorder(
          borderRadius  : BorderRadius.circular(8),
          borderSide    : const BorderSide(color: PlegmaColors.border),
        ),
        focusedBorder   : OutlineInputBorder(
          borderRadius  : BorderRadius.circular(8),
          borderSide    : const BorderSide(color: PlegmaColors.cyan, width: 1.5),
        ),
        labelStyle      : const TextStyle(color: PlegmaColors.textDim, fontSize: 12),
        hintStyle       : const TextStyle(color: PlegmaColors.textDim, fontSize: 12),
        contentPadding  : const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor   : PlegmaColors.cyan,
          foregroundColor   : Colors.black,
          shape             : RoundedRectangleBorder(
            borderRadius    : BorderRadius.circular(8),
          ),
          textStyle         : const TextStyle(
            fontWeight      : FontWeight.bold,
            letterSpacing   : 2,
            fontSize        : 12,
          ),
          padding           : const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
          elevation         : 0,
        ),
      ),
      dividerTheme: const DividerThemeData(
        color     : PlegmaColors.border,
        thickness : 1,
        space     : 1,
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: CupertinoPageTransitionsBuilder(),
          TargetPlatform.iOS    : CupertinoPageTransitionsBuilder(),
        },
      ),
    );
  }
}
