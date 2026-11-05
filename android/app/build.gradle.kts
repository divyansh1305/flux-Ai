plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.flux.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.flux.companion"
        minSdk = 26
        targetSdk = 35
        versionCode = 4
        versionName = "0.4.0"
    }

    // Release signing comes from GitHub secrets (see docs/DEPLOY.md). Without them, only the debug build is made.
    val keystorePath = System.getenv("KITNA_KEYSTORE")
    signingConfigs {
        if (keystorePath != null && file(keystorePath).exists()) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("KITNA_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KITNA_KEY_ALIAS") ?: "kitna"
                keyPassword = System.getenv("KITNA_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            // The app is tiny and has no libraries to shrink; no minify means no surprises from code stripping.
            isMinifyEnabled = false
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Deliberately tiny: no third-party libraries, so there's nothing that could leak data.
    implementation("androidx.core:core-ktx:1.13.1")
}
