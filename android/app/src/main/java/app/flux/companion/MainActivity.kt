package app.flux.companion

import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.concurrent.Executors

/**
 * One screen, built in code (no layout XML to keep the app tiny):
 *   1. Prominent disclosure + explicit consent (Google Play User Data policy).
 *   2. Link the account: one tap on "Link the Kitna Companion app" in Kitna web (a fluxapp://connect link), or paste by hand.
 *   3. Button to open Settings → Notification access.
 *   4. Status: access granted? connected? items waiting?
 */
class MainActivity : Activity() {

    private lateinit var store: SecureStore
    private lateinit var status: TextView
    private val io = Executors.newSingleThreadExecutor()

    private val bg = Color.parseColor("#F6F4EF")
    private val card = Color.parseColor("#FFFFFF")
    private val fg = Color.parseColor("#1D1C1A")
    private val muted = Color.parseColor("#5F5B54")
    private val accent = Color.parseColor("#245C43")
    private var linkMessage: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = SecureStore(this)
        if (store.serverUrl.isEmpty()) store.serverUrl = OFFICIAL_SERVER
        handleLink(intent)
        render()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLink(intent)
        render()
    }

    /** fluxapp://connect?server=…&token=… from the Kitna website. Only the official server is accepted, so a
     *  link from anywhere else can never point this phone's payments at someone else's server. */
    private fun handleLink(intent: Intent?) {
        val data: Uri = intent?.data ?: return
        if (data.scheme != "fluxapp" || data.host != "connect") return
        val server = data.getQueryParameter("server")?.trim()?.trimEnd('/') ?: ""
        val token = data.getQueryParameter("token")?.trim() ?: ""
        if (server !in OFFICIAL_SERVERS || !token.startsWith("flx_") || token.length > 200) {
            linkMessage = "That link didn't come from Kitna, so nothing was changed."
            return
        }
        store.serverUrl = server
        store.token = token
        linkMessage = "Phone linked to your Kitna account. Last step: turn on notification access below."
        io.execute {
            val msg = Uploader(this).ping(server, token)
            runOnUiThread { linkMessage = msg; if (::status.isInitialized) refreshStatus() }
        }
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    private fun render() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(28), dp(20), dp(28))
            setBackgroundColor(bg)
        }
        root.addView(text("Kitna Companion", 26f, fg, bold = true))
        root.addView(text("Logs your UPI and bank payments into Kitna automatically.", 15f, muted).apply { pad(top = 6) })

        // 1. Disclosure – shown before any access is requested
        root.addView(section("What this app reads"))
        root.addView(text(
            "• Kitna Companion reads the text of notifications from payment and bank apps only " +
                "(Google Pay, PhonePe, Paytm, BHIM, CRED, Amazon Pay, bank apps, and bank SMS shown by your Messages app).\n" +
                "• It keeps only notifications that look like a completed payment: an amount plus words like " +
                "\"debited\", \"paid\" or \"received\". OTPs, chats, offers and reminders are ignored on your phone and never sent.\n" +
                "• The matched text is sent over HTTPS to your own Kitna account, to add the transaction to your ledger.\n" +
                "• Nothing is sold, shared or used for ads. Turn it off any time in Settings → Notification access, " +
                "or revoke the token in Kitna.",
            14f, fg
        ).apply { boxed() })

        val consent = CheckBox(this).apply {
            text = "I understand and allow Kitna Companion to read payment notifications"
            setTextColor(fg)
            isChecked = store.consented
            buttonTintList = android.content.res.ColorStateList.valueOf(accent)
            setOnCheckedChangeListener { _, on -> store.consented = on; refreshStatus() }
        }
        root.addView(consent.apply { pad(top = 10) })

        // 2. Link account
        root.addView(section("Link your Kitna account"))
        root.addView(text("Easiest: open Kitna in your browser → Settings → Android → \"Link the Kitna Companion app\". It opens this app and links it by itself.", 14f, muted))
        root.addView(button("Open Kitna in the browser", secondary = true) {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("$OFFICIAL_SERVER/app/settings#auto")))
        })
        root.addView(text("Or paste it by hand:", 13f, muted).apply { pad(top = 14) })
        val server = input(OFFICIAL_SERVER, store.serverUrl, InputType.TYPE_TEXT_VARIATION_URI)
        val token = input("flx_… token from Kitna → Settings → Auto-log", "", InputType.TYPE_TEXT_VARIATION_PASSWORD)
        if (store.token != null) token.hint = "Token saved (paste a new one to replace)"
        root.addView(server)
        root.addView(token.apply { pad(top = 8) })
        root.addView(button("Save & test connection") {
            val url = server.text.toString().trim()
            if (!url.startsWith("https://")) { status.text = "Server must start with https://"; return@button }
            store.serverUrl = url
            if (token.text.isNotBlank()) store.token = token.text.toString()
            token.setText("")
            val t = store.token ?: run { status.text = "Paste your token first"; return@button }
            status.text = "Testing…"
            io.execute {
                val msg = Uploader(this).ping(store.serverUrl, t)
                runOnUiThread { status.text = msg; Uploader(this).flushAsync() }
            }
        })

        // 3. Notification access
        root.addView(section("Turn it on"))
        root.addView(text("On the next screen, tap Kitna Companion and allow it.", 14f, muted))
        root.addView(button("Open Notification access settings") {
            if (!store.consented) { status.text = "Please tick the consent box first"; return@button }
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        root.addView(text(
            "If Android says \"Restricted setting\": this happens with apps installed from a link instead of the Play Store. " +
                "Tap the button below, then ⋮ (top right) → Allow restricted settings, and come back.",
            13f, muted
        ).apply { pad(top = 10) })
        root.addView(button("Open app info", secondary = true) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        root.addView(button("Unlink this phone", secondary = true) {
            store.token = null
            store.consented = false
            consent.isChecked = false
            status.text = "Unlinked. Also revoke the token in Kitna if you lost this phone."
        })

        // 4. Status
        status = text("", 14f, fg).apply { pad(top = 18) }
        root.addView(status)
        refreshStatus()

        setContentView(ScrollView(this).apply { setBackgroundColor(bg); addView(root) })
    }

    private fun refreshStatus() {
        val granted = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
            ?.contains(ComponentName(this, FluxNotificationListener::class.java).flattenToString()) == true
        val lines = listOf(
            (if (store.consented) "✓" else "✗") + " Consent given",
            (if (store.token != null && store.serverUrl.isNotEmpty()) "✓" else "✗") + " Account linked",
            (if (granted) "✓" else "✗") + " Notification access on",
            "Waiting to upload: ${Uploader(this).pendingCount()}",
        )
        status.text = (listOfNotNull(linkMessage) + lines).joinToString("\n")
    }

    // ---- tiny view helpers ----
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun text(s: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
        setLineSpacing(0f, 1.25f)
    }

    private fun section(s: String) = text(s.uppercase(), 12f, muted, bold = true).apply { pad(top = 26, bottom = 8) }

    private fun input(hint: String, value: String, type: Int) = EditText(this).apply {
        this.hint = hint; setText(value); setTextColor(fg); setHintTextColor(muted)
        inputType = InputType.TYPE_CLASS_TEXT or type
        setSingleLine(); boxed()
    }

    private fun button(label: String, secondary: Boolean = false, onClick: () -> Unit) = Button(this).apply {
        text = label; isAllCaps = false; textSize = 15f
        setTextColor(if (secondary) fg else Color.WHITE)
        setBackgroundColor(if (secondary) card else accent)
        setOnClickListener { onClick() }
        layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(50)).apply { topMargin = dp(10) }
        gravity = Gravity.CENTER
    }

    private fun View.boxed() {
        setBackgroundColor(card); setPadding(dp(14), dp(12), dp(14), dp(12))
    }

    companion object {
        const val OFFICIAL_SERVER = "https://fluxai.pythonanywhere.com"
        /** The current address, plus the planned kitna address, so a move needs no app update. */
        val OFFICIAL_SERVERS = setOf(OFFICIAL_SERVER, "https://kitna.pythonanywhere.com")
    }

    private fun View.pad(top: Int = 0, bottom: Int = 0) {
        val lp = (layoutParams as? LinearLayout.LayoutParams)
            ?: LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        lp.topMargin = dp(top); lp.bottomMargin = dp(bottom); layoutParams = lp
    }
}
