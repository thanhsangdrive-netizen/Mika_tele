package com.wangzan101.mika.telegram

import android.util.Log
import com.wangzan101.mika.core.run.Channel
import com.wangzan101.mika.core.run.ChannelInput
import com.wangzan101.mika.core.run.ChannelInputSink
import com.wangzan101.mika.core.run.ChannelPeer
import com.wangzan101.mika.core.run.Delivery
import com.wangzan101.mika.core.run.SendOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class TelegramChannel(
    private val store: TelegramStore,
    private val client: OkHttpClient,
    private val activeAsk: (String) -> Delivery.Ask? = { null },
) : Channel {
    override val id = ID
    override val confirms = false
    @Volatile private var sink: ChannelInputSink? = null

    override fun isAlive(peer: ChannelPeer): Boolean {
        return peer.channelId == id && store.enabled.value && store.isConfigured() &&
                (store.ownerId.value.isBlank() || peer.peerId == store.ownerId.value)
    }

    override fun start(sink: ChannelInputSink): AutoCloseable {
        this.sink = sink
        return AutoCloseable { if (this.sink === sink) this.sink = null }
    }

    override suspend fun send(peer: ChannelPeer, delivery: Delivery): SendOutcome = withContext(Dispatchers.IO) {
        val token = store.botToken.value
        val chatId = peer.peerId.takeIf { it.isNotBlank() } ?: store.ownerId.value
        if (token.isBlank() || chatId.isBlank()) return@withContext SendOutcome.Failed

        val text = when (delivery) {
            is Delivery.Ask -> "❓ *Mika cần bạn trả lời:*\n\n${delivery.text}\n\n👉 _Hãy trả lời trực tiếp tin nhắn này._"
            is Delivery.Result -> "✅ *Hoàn thành tác vụ:*\n\n${delivery.text}"
            is Delivery.Progress -> "⚡ *Đang thực hiện:* ${delivery.text}"
            is Delivery.Notice -> "ℹ️ ${delivery.text}"
        }

        try {
            sendTelegramMessage(token, chatId, text)
            SendOutcome.Delivered
        } catch (e: CancellationException) {
            throw e
        } catch (t: Throwable) {
            Log.e(TAG, "sendTelegramMessage failed", t)
            SendOutcome.Failed
        }
    }

    suspend fun pollOnce(): Int = withContext(Dispatchers.IO) {
        val input = sink ?: return@withContext 0
        val token = store.botToken.value
        if (token.isBlank() || !store.enabled.value) return@withContext 0

        val offset = store.lastUpdateId + 1
        val url = "https://api.telegram.org/bot$token/getUpdates?offset=$offset&timeout=20"
        val request = Request.Builder().url(url).build()

        val response = try {
            client.newCall(request).execute()
        } catch (e: CancellationException) {
            throw e
        } catch (t: Throwable) {
            Log.w(TAG, "Telegram poll failed: ${t.message}")
            return@withContext 0
        }

        val body = response.body?.string() ?: return@withContext 0
        val json = try { JSONObject(body) } catch (e: Exception) { return@withContext 0 }
        if (!json.optBoolean("ok")) return@withContext 0

        val results = json.optJSONArray("result") ?: return@withContext 0
        var count = 0

        for (i in 0 until results.length()) {
            val item = results.optJSONObject(i) ?: continue
            val updateId = item.optLong("update_id")
            if (updateId > store.lastUpdateId) {
                store.lastUpdateId = updateId
            }

            val message = item.optJSONObject("message") ?: continue
            val from = message.optJSONObject("from") ?: continue
            if (from.optBoolean("is_bot")) continue

            val senderId = from.optLong("id").toString()
            val text = message.optString("text", "").trim()
            val messageId = message.optLong("message_id").toString()

            // Tự động gán chủ sở hữu lần đầu nếu chưa điền Owner ID
            if (store.ownerId.value.isBlank()) {
                store.setOwnerId(senderId)
                sendTelegramMessage(token, senderId, "🎉 *Ghép nối thành công!*\nTừ bây giờ, bạn có thể gửi yêu cầu điều khiển điện thoại cho Mika qua đoạn chat này.")
            }

            if (senderId != store.ownerId.value) continue

            val peer = ChannelPeer(ID, senderId, "tg-$senderId")
            val askId = activeAsk(peer.threadId)?.askId

            if (text == "/start" || text == "/help") {
                sendTelegramMessage(token, senderId, """
                    👋 *Trợ lý Mika trên điện thoại đã sẵn sàng!*
                    
                    Gửi bất kỳ yêu cầu nào để Mika thực hiện trên điện thoại:
                    • _"Đặt báo thức 7h sáng mai"_
                    • _"Mở YouTube bật nhạc Lofi"_
                    • _"Kiểm tra thời tiết hôm nay"_
                    
                    *Các lệnh hỗ trợ:*
                    /status - Xem trạng thái tác vụ
                    /cancel - Hủy tác vụ đang chạy
                    /help - Xem hướng dẫn này
                """.trimIndent())
                count++
                continue
            }

            if (text.isNotBlank()) {
                input.receive(ChannelInput.Text(peer, messageId, text, askId))
                count++
            }
        }

        count
    }

    private fun sendTelegramMessage(token: String, chatId: String, text: String) {
        val payload = JSONObject().apply {
            put("chat_id", chatId)
            put("text", text)
            put("parse_mode", "Markdown")
        }
        val req = Request.Builder()
            .url("https://api.telegram.org/bot$token/sendMessage")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                // Retry without markdown if parsing failed
                val fallbackPayload = JSONObject().apply {
                    put("chat_id", chatId)
                    put("text", text.replace("*", "").replace("_", ""))
                }
                val retryReq = Request.Builder()
                    .url("https://api.telegram.org/bot$token/sendMessage")
                    .post(fallbackPayload.toString().toRequestBody("application/json".toMediaType()))
                    .build()
                client.newCall(retryReq).execute().close()
            }
        }
    }

    companion object {
        const val ID = "telegram"
        private const val TAG = "MikaTelegram"
    }
}
