package app.flux.companion

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the ingest token encrypted with an AES-256-GCM key that lives in the
 * Android Keystore (hardware-backed on most phones). The key never leaves the
 * secure hardware, so a copied prefs file is useless.
 * (androidx.security-crypto is deprecated, so this is the ~40-line replacement.)
 */
class SecureStore(context: Context) {

    private val prefs = context.getSharedPreferences("flux_secure", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    fun putSecret(name: String, value: String?) {
        if (value.isNullOrEmpty()) {
            prefs.edit().remove(name).apply(); return
        }
        val cipher = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val enc = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val blob = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(enc, Base64.NO_WRAP)
        prefs.edit().putString(name, blob).apply()
    }

    fun getSecret(name: String): String? {
        val blob = prefs.getString(name, null) ?: return null
        return try {
            val (iv, data) = blob.split(":").map { Base64.decode(it, Base64.NO_WRAP) }
            val cipher = Cipher.getInstance(TRANSFORM).apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            }
            String(cipher.doFinal(data), Charsets.UTF_8)
        } catch (e: Exception) {
            null // key was reset (e.g. new lock screen) – user just pastes the token again
        }
    }

    // Non-secret settings
    var serverUrl: String
        get() = prefs.getString("server", "") ?: ""
        set(v) = prefs.edit().putString("server", v.trim().trimEnd('/')).apply()

    var consented: Boolean
        get() = prefs.getBoolean("consented", false)
        set(v) = prefs.edit().putBoolean("consented", v).apply()

    var token: String?
        get() = getSecret("token")
        set(v) = putSecret("token", v?.trim())

    companion object {
        private const val ALIAS = "flux_token_key"
        private const val TRANSFORM = "AES/GCM/NoPadding"
    }
}
