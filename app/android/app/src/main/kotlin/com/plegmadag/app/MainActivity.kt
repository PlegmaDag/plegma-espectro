package com.plegmadag.app

import android.app.AppOpsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.security.MessageDigest

class MainActivity : FlutterFragmentActivity() {

    // ── Canais de comunicação ─────────────────────────────────────────────────
    private val SHIELD_CHANNEL   = "com.plegmadag.app/shield"
    private val PKG_EVENTS_CHANNEL = "com.plegmadag.app/package_events"

    // Permissões sensíveis monitoradas
    private val SENSITIVE_PERMISSIONS = listOf(
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.READ_CONTACTS",
        "android.permission.READ_SMS",
        "android.permission.SEND_SMS",
        "android.permission.READ_CALL_LOG",
        "android.permission.READ_PHONE_STATE",
        "android.permission.READ_MEDIA_IMAGES",
        "android.permission.READ_EXTERNAL_STORAGE",
    )

    // ── BroadcastReceiver para mudanças de pacotes ────────────────────────────
    private var packageEventSink: EventChannel.EventSink? = null

    private val packageChangeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val pkg = intent.data?.schemeSpecificPart ?: return
            val action = when (intent.action) {
                Intent.ACTION_PACKAGE_ADDED    -> "ADDED"
                Intent.ACTION_PACKAGE_REMOVED  -> "REMOVED"
                Intent.ACTION_PACKAGE_CHANGED  -> "CHANGED"
                Intent.ACTION_PACKAGE_REPLACED -> "CHANGED"
                else -> return
            }
            packageEventSink?.success(mapOf("action" to action, "package" to pkg))
        }
    }

    // ── Configuração do Flutter Engine ────────────────────────────────────────
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // MethodChannel: leitura de apps e permissões
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SHIELD_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getInstalledApps" -> {
                        try { result.success(getInstalledApps()) }
                        catch (e: Exception) { result.error("SCAN_ERROR", e.message, null) }
                    }
                    "getAppsWithSensitivePermissions" -> {
                        try { result.success(getAppsWithSensitivePermissions()) }
                        catch (e: Exception) { result.error("PERM_ERROR", e.message, null) }
                    }
                    "computeStateHash" -> {
                        val data = call.arguments as? String ?: ""
                        result.success(computeStateHash(data))
                    }
                    "openAppSettings" -> {
                        val pkg = call.arguments as? String ?: ""
                        try {
                            val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                data = Uri.fromParts("package", pkg, null)
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            startActivity(intent)
                            result.success(true)
                        } catch (e: Exception) {
                            result.error("SETTINGS_ERROR", e.message, null)
                        }
                    }
                    "requestIgnoreBatteryOptimizations" -> {
                        try {
                            val pm = getSystemService(POWER_SERVICE) as PowerManager
                            if (pm.isIgnoringBatteryOptimizations(packageName)) {
                                result.success(false) // já isento — nada a fazer
                            } else {
                                val intent = Intent(
                                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
                                ).apply {
                                    data = Uri.parse("package:$packageName")
                                }
                                startActivity(intent)
                                result.success(true) // diálogo aberto
                            }
                        } catch (e: Exception) {
                            result.error("BATTERY_OPT_ERROR", e.message, null)
                        }
                    }
                    else -> result.notImplemented()
                }
            }

        // EventChannel: stream de mudanças de pacotes
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, PKG_EVENTS_CHANNEL)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, sink: EventChannel.EventSink) {
                    packageEventSink = sink
                    registerPackageReceiver()
                }
                override fun onCancel(arguments: Any?) {
                    packageEventSink = null
                    unregisterPackageReceiver()
                }
            })
    }

    // ── Registro do BroadcastReceiver ─────────────────────────────────────────
    private fun registerPackageReceiver() {
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_PACKAGE_ADDED)
            addAction(Intent.ACTION_PACKAGE_REMOVED)
            addAction(Intent.ACTION_PACKAGE_CHANGED)
            addAction(Intent.ACTION_PACKAGE_REPLACED)
            addDataScheme("package")
        }
        registerReceiver(packageChangeReceiver, filter)
    }

    private fun unregisterPackageReceiver() {
        try { unregisterReceiver(packageChangeReceiver) } catch (_: Exception) {}
    }

    override fun onDestroy() {
        unregisterPackageReceiver()
        super.onDestroy()
    }

    // ── Apps instalados (para snapshot e scanner) ─────────────────────────────
    private fun getInstalledApps(): List<Map<String, Any>> {
        val pm = packageManager
        val sigFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)
            PackageManager.GET_SIGNING_CERTIFICATES
        else
            @Suppress("DEPRECATION") PackageManager.GET_SIGNATURES

        val packages: List<PackageInfo> =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                pm.getInstalledPackages(PackageManager.PackageInfoFlags.of(sigFlag.toLong()))
            else
                @Suppress("DEPRECATION") pm.getInstalledPackages(sigFlag)

        return packages.mapNotNull { pkg ->
            val appInfo = pkg.applicationInfo ?: return@mapNotNull null
            val isSystem = (appInfo.flags and ApplicationInfo.FLAG_SYSTEM) != 0
            if (isSystem) return@mapNotNull null   // exclui sistema
            try {
                mapOf(
                    "package_name" to pkg.packageName,
                    "app_name"     to pm.getApplicationLabel(appInfo).toString(),
                    "cert_hash"    to getCertHash(pkg),
                    "version"      to (pkg.versionName ?: ""),
                )
            } catch (_: Exception) { null }
        }
    }

    // ── Apps com permissões sensíveis concedidas (para monitor) ──────────────
    private fun getAppsWithSensitivePermissions(): List<Map<String, Any>> {
        val pm      = packageManager
        val appOps  = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager

        val packages: List<PackageInfo> =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                pm.getInstalledPackages(PackageManager.PackageInfoFlags.of(
                    PackageManager.GET_PERMISSIONS.toLong()))
            else
                @Suppress("DEPRECATION") pm.getInstalledPackages(PackageManager.GET_PERMISSIONS)

        // Mapa: permissão → opstr do AppOps (para checar "somente quando em uso")
        val permToOps = mapOf(
            "android.permission.CAMERA"       to AppOpsManager.OPSTR_CAMERA,
            "android.permission.RECORD_AUDIO" to AppOpsManager.OPSTR_RECORD_AUDIO,
        )

        return packages.mapNotNull { pkg ->
            val appInfo = pkg.applicationInfo ?: return@mapNotNull null
            val isSystem = (appInfo.flags and ApplicationInfo.FLAG_SYSTEM) != 0
            if (isSystem) return@mapNotNull null

            val declared = pkg.requestedPermissions?.toList() ?: return@mapNotNull null
            val uid      = appInfo.uid

            val granted = SENSITIVE_PERMISSIONS.filter { perm ->
                declared.contains(perm) &&
                pm.checkPermission(perm, pkg.packageName) == PackageManager.PERMISSION_GRANTED
            }.map { it.removePrefix("android.permission.") }

            if (granted.isEmpty()) return@mapNotNull null

            // Detecta permissões concedidas apenas "enquanto em uso"
            val whileInUse = mutableListOf<String>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Android 10+ não permite acesso em segundo plano à câmera ou
                // microfone para apps comuns — são inerentemente "somente em uso".
                // Em vez de depender de AppOps (que pode falhar), verificamos se o
                // app NÃO declarou uma permissão de background equivalente.
                // Câmera: não existe "background camera" permission padrão → sempre foreground.
                // Microfone: idem — background audio exigiria permissão de sistema especial.
                if (granted.contains("CAMERA"))       whileInUse.add("CAMERA")
                if (granted.contains("RECORD_AUDIO")) whileInUse.add("RECORD_AUDIO")

                // Para outros ops futuros, mantém a verificação via AppOps como fallback
                permToOps
                    .filterKeys { it != "android.permission.CAMERA" && it != "android.permission.RECORD_AUDIO" }
                    .forEach { (perm, opStr) ->
                        val shortPerm = perm.removePrefix("android.permission.")
                        if (granted.contains(shortPerm)) {
                            val mode = try {
                                @Suppress("DEPRECATION")
                                appOps.unsafeCheckOpNoThrow(opStr, uid, pkg.packageName)
                            } catch (_: Exception) { 4 } // default: assume foreground
                            if (mode == 4) whileInUse.add(shortPerm)
                        }
                    }
            }

            mapOf(
                "package_name"           to pkg.packageName,
                "app_name"               to pm.getApplicationLabel(appInfo).toString(),
                "permissions"            to granted,
                "permissions_while_in_use" to whileInUse,
            )
        }
    }

    // ── Hash do estado (BLAKE3-compatible) ───────────────────────────────────
    // Replica a hierarquia do Python: SHA3-256 (API 31+) → SHA-256 fallback.
    // BLAKE3 exigiria biblioteca nativa; SHA3-256 é equivalente ao fallback
    // já usado em lattice_shield.py / auth_server.py quando blake3 não está
    // disponível no servidor.
    private fun computeStateHash(data: String): String {
        val bytes = data.toByteArray(Charsets.UTF_8)
        val algorithm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            "SHA3-256"   // Android 12+ — espelho do fallback Python
        } else {
            "SHA-256"    // Android < 12 — último recurso
        }
        return try {
            MessageDigest.getInstance(algorithm)
                .digest(bytes)
                .joinToString("") { "%02x".format(it) }
        } catch (_: Exception) {
            // Segurança extra: se SHA3-256 falhar por algum motivo, usa SHA-256
            MessageDigest.getInstance("SHA-256")
                .digest(bytes)
                .joinToString("") { "%02x".format(it) }
        }
    }

    // ── SHA-256 do certificado de assinatura ──────────────────────────────────
    private fun getCertHash(pkg: PackageInfo): String {
        return try {
            val certBytes: ByteArray? =
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)
                    pkg.signingInfo?.apkContentsSigners?.firstOrNull()?.toByteArray()
                else
                    @Suppress("DEPRECATION") pkg.signatures?.firstOrNull()?.toByteArray()

            certBytes?.let {
                MessageDigest.getInstance("SHA-256").digest(it)
                    .joinToString("") { b -> "%02x".format(b) }
            } ?: ""
        } catch (_: Exception) { "" }
    }
}
