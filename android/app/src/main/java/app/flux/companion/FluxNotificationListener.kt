package app.flux.companion

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Runs only after the user grants Notification access. Reads the text of
 * payment notifications, filters on-device (see Filter), and hands matches
 * to the Uploader. Nothing is stored except the short retry queue.
 */
class FluxNotificationListener : NotificationListenerService() {

    private val recent = ArrayDeque<String>()   // apps often re-post the same notification

    override fun onListenerConnected() {
        Uploader(this).flushAsync()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val store = SecureStore(this)
        if (!store.consented) return

        val pkg = sbn.packageName ?: return
        if (pkg !in Filter.PACKAGES) return

        val extras = sbn.notification?.extras ?: return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val body = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
        val text = "$title. $body".trim()

        if (!Filter.shouldSend(pkg, text)) return

        val key = "$pkg|$text"
        synchronized(recent) {
            if (key in recent) return
            recent.addLast(key)
            if (recent.size > 30) recent.removeFirst()
        }
        Uploader(this).enqueueAndFlush(pkg, title, body, sbn.postTime)
    }
}
