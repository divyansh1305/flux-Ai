package app.flux.companion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Sends filtered notifications to POST {server}/api/ingest/notification.
 * If the phone is offline, items wait in a small local queue (max 200) and
 * are retried next time. The server dedupes by reference/amount, so a retry
 * can never create a double entry.
 */
class Uploader(private val context: Context) {

    private val store = SecureStore(context)
    private val queueFile = File(context.filesDir, "pending.json")

    fun enqueueAndFlush(pkg: String, title: String, text: String, postedAt: Long) {
        io.execute {
            synchronized(lock) {
                val q = readQueue()
                q.put(JSONObject().put("package", pkg).put("title", title).put("body", text).put("posted_at", postedAt))
                while (q.length() > 200) q.remove(0)
                writeQueue(q)
            }
            flush()
        }
    }

    fun flushAsync() = io.execute { flush() }

    private fun flush() {
        val server = store.serverUrl
        val token = store.token
        if (server.isEmpty() || token.isNullOrEmpty() || !store.consented) return
        synchronized(lock) {
            val q = readQueue()
            val left = JSONArray()
            for (i in 0 until q.length()) {
                val item = q.getJSONObject(i)
                when (post("$server/api/ingest/notification", token, item)) {
                    Result.OK, Result.DROP -> Unit       // done, or server says it's junk
                    Result.RETRY -> left.put(item)       // offline / 5xx / rate-limited
                }
            }
            writeQueue(left)
        }
    }

    enum class Result { OK, RETRY, DROP }

    private fun post(url: String, token: String, body: JSONObject): Result = try {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10_000
            readTimeout = 15_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Authorization", "Bearer $token")
        }
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = conn.responseCode
        conn.disconnect()
        when {
            code in 200..299 -> Result.OK
            code == 429 || code >= 500 -> Result.RETRY
            else -> Result.DROP   // 400 not a payment, 401 bad token (user re-links in app)
        }
    } catch (e: Exception) {
        Result.RETRY
    }

    /** Used by the "Test connection" button. Returns the server's greeting or an error. */
    fun ping(server: String, token: String): String = try {
        val conn = (URL("${server.trimEnd('/')}/api/ingest/ping").openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 10_000
            setRequestProperty("Authorization", "Bearer $token")
        }
        val code = conn.responseCode
        val text = (if (code in 200..299) conn.inputStream else conn.errorStream)?.bufferedReader()?.readText() ?: ""
        conn.disconnect()
        if (code == 200) "Connected as ${JSONObject(text).optString("name")}" else "Server said $code – check the token"
    } catch (e: Exception) {
        "Can't reach server: ${e.message}"
    }

    fun pendingCount(): Int = synchronized(lock) { readQueue().length() }

    private fun readQueue(): JSONArray =
        try { JSONArray(queueFile.readText()) } catch (e: Exception) { JSONArray() }

    private fun writeQueue(q: JSONArray) = queueFile.writeText(q.toString())

    companion object {
        private val io = Executors.newSingleThreadExecutor()
        private val lock = Any()
    }
}
