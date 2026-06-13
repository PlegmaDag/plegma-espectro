plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.plegmadag.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    signingConfigs {
        create("release") {
            storeFile     = file("plegma-release.keystore")
            storePassword = "plegma2026"
            keyAlias      = "plegma"
            keyPassword   = "plegma2026"
        }
    }

    // CVE-007/008 PATCH: build da libdilithium_plegma.so via NDK + CMake
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    defaultConfig {
        applicationId = "com.plegmadag.app"
        minSdk = flutter.minSdkVersion
        targetSdk     = flutter.targetSdkVersion
        versionCode   = 1
        versionName   = "1.0.0"

        // Alvos ABI: ARM64 (produção) + x86_64 (emulador)
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            signingConfig   = signingConfigs.getByName("release")
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }
}

flutter {
    source = "../.."
}
