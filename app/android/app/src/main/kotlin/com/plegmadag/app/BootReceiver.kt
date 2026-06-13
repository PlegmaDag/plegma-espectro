package com.plegmadag.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        // Lê SharedPreferences do Flutter (prefixo "flutter." obrigatório)
        val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val validadorAtivo = prefs.getBoolean("flutter.validador_ativo", false)
        if (!validadorAtivo) return

        // Inicia o BackgroundService do flutter_background_service
        try {
            val serviceClass = Class.forName("id.flutter.flutter_background_service.BackgroundService")
            val serviceIntent = Intent(context, serviceClass)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
        } catch (e: Exception) {
            // Serviço não encontrado — sem crash
        }
    }
}
