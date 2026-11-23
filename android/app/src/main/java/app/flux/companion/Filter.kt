package app.flux.companion

import android.content.Context
import android.provider.Telephony

/**
 * On-device filter. A notification leaves the phone only if ALL of these hold:
 *  1. it comes from a known payment / bank app (allow-list below),
 *  2. it mentions a rupee amount,
 *  3. it reads like a completed debit or credit,
 *  4. it is not an OTP, offer, reminder or failed payment.
 * Everything else (chats, OTPs, promos) is dropped here and never sent.
 *
 * Keep PACKAGES in sync with NOTIFICATION_PACKAGES on the server
 * (flux/api/ingest.py) – the server rejects anything else anyway.
 */
object Filter {

    val PACKAGES: Map<String, String> = mapOf(
        "com.google.android.apps.nbu.paisa.user" to "Google Pay",
        "com.phonepe.app" to "PhonePe",
        "net.one97.paytm" to "Paytm",
        "in.org.npci.upiapp" to "BHIM",
        "in.amazon.mShop.android.shopping" to "Amazon Pay",
        "com.dreamplug.androidapp" to "CRED",
        "money.super.payments" to "super.money",
        "com.whatsapp" to "WhatsApp Pay",
        "com.sbi.lotusintouch" to "YONO SBI",
        "com.csam.icici.bank.imobile" to "ICICI iMobile",
        "com.snapwork.hdfc" to "HDFC Bank",
        "com.axis.mobile" to "Axis Mobile",
        "com.msf.kbank.mobile" to "Kotak",
        "com.google.android.apps.messaging" to "Messages",  // bank SMS shown as notifications
        "com.samsung.android.messaging" to "Samsung Messages",
        "com.android.mms" to "Messages",            // Xiaomi / Redmi / POCO and other built-in SMS apps
        "com.oneplus.mms" to "OnePlus Messages",
        "com.truecaller" to "Truecaller",
    )

    /** The phone's default SMS app, whatever the brand (Vivo, Oppo, Realme...). Null if none. */
    fun defaultSmsApp(context: Context): String? =
        try { Telephony.Sms.getDefaultSmsPackage(context) } catch (e: Exception) { null }

    /** A known payment app, or the phone's own SMS app showing a bank SMS. */
    fun isWatched(context: Context, packageName: String): Boolean =
        packageName in PACKAGES || packageName == defaultSmsApp(context)

    private val AMOUNT = Regex("""(?i)(₹|rs\.?|inr)\s*:?\s*[0-9][0-9,]*(\.[0-9]{1,2})?""")
    private val MONEY_WORDS = Regex(
        """(?i)\b(debited|credited|paid|sent|received|spent|withdrawn|deposited|transferred|payment (of|to)|refund)\b"""
    )
    private val SKIP = Regex(
        """(?i)\b(otp|one[- ]time password|verification code|offer|cashback up to|win|reward points|request(ed)? (money|payment)|collect request|failed|declined|reminder|due (on|date)|will be debited|is due|auto-?pay (set|scheduled))\b"""
    )

    fun shouldSend(context: Context, packageName: String, text: String): Boolean {
        if (!isWatched(context, packageName)) return false
        if (text.length < 12 || text.length > 1000) return false
        if (SKIP.containsMatchIn(text)) return false
        return AMOUNT.containsMatchIn(text) && MONEY_WORDS.containsMatchIn(text)
    }
}
