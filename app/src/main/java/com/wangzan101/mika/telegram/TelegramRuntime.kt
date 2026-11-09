package com.wangzan101.mika.telegram

import android.content.Context
import android.util.Log
import com.wangzan101.mika.MikaApp
import com.wangzan101.mika.core.action.ConfirmChoice
import com.wangzan101.mika.core.run.ChannelGateway
import com.wangzan101.mika.core.run.ChannelPeer
import com.wangzan101.mika.core.run.MemoryOwnerIdentity
import com.wangzan101.mika.core.run.RunId
import com.wangzan101.mika.core.net.NetProxy
import com.wangzan101.mika.task.TaskService
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

sealed interface TelegramConnectionState {
    data object Off : TelegramConnectionState
    data object NotConfigured : TelegramConnectionState
    data object Connecting : TelegramConnectionState
    data class Connected(val username: String) : TelegramConnectionState
    data class Failed(val reason: String) : TelegramConnectionState
}

class TelegramRuntime(
    private val context: Context,
    val store: TelegramStore,
    client: OkHttpClient? = null,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val http = client ?: NetProxy.shared.client(
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .readTimeout(35, TimeUnit.SECONDS)
    )

    private val owners = MemoryOwnerIdentity()
    private val app get() = context.applicationContext as MikaApp

    private val gateway = ChannelGateway(
        owners,
        { threadId -> app.taskState.run(threadId)?.activeAsk },
        object : ChannelGateway.Route {
            override suspend fun newTask(peer: ChannelPeer, messageId: String, text: String) {
                TaskService.startChannel(context, peer, messageId, text)
            }

            override suspend fun answer(threadId: String, askId: String, text: String): Boolean {
                return app.taskState.run(threadId)?.answerFromChannel(text, askId) == true
            }

            override suspend fun confirm(threadId: String, askId: String, choice: ConfirmChoice): Boolean = false

            override suspend fun stop(runId: RunId) {
                TaskService.cancel(context, runId.value)
            }

            override suspend fun cancelAsk(threadId: String) {
                val run = app.taskState.run(threadId) ?: return
                run.activeAsk?.askId?.let(run::cancelAsk)
            }
        }
    )

    val channel = TelegramChannel(
        store,
        http,
        activeAsk = { threadId -> app.taskState.run(threadId)?.activeAsk }
    )

    private var registration: AutoCloseable? = null
    private var pollJob: Job? = null

    private val _state = MutableStateFlow<TelegramConnectionState>(
        if (!store.isConfigured()) TelegramConnectionState.NotConfigured
        else if (store.enabled.value) TelegramConnectionState.Connecting
        else TelegramConnectionState.Off
    )
    val state: StateFlow<TelegramConnectionState> = _state.asStateFlow()

    fun channelFor(id: String) = channel.takeIf { id == TelegramChannel.ID }

    suspend fun testAndSave(token: String, ownerId: String): Result<String> = withContext(Dispatchers.IO) {
        val cleanToken = token.trim()
        if (cleanToken.isBlank()) return@withContext Result.failure(IllegalArgumentException("Token cannot be empty"))

        val req = Request.Builder()
            .url("https://api.telegram.org/bot$cleanToken/getMe")
            .build()

        try {
            http.newCall(req).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                val json = JSONObject(body)
                if (json.optBoolean("ok")) {
                    val result = json.getJSONObject("result")
                    val username = result.optString("username", "")
                    store.saveConfig(cleanToken, ownerId, username)
                    sync()
                    Result.success(username)
                } else {
                    val desc = json.optString("description", "Invalid bot token")
                    Result.failure(Exception(desc))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    @Synchronized
    fun sync() {
        if (!store.isConfigured()) {
            stop()
            _state.value = TelegramConnectionState.NotConfigured
            return
        }
        if (!store.enabled.value) {
            stop()
            _state.value = TelegramConnectionState.Off
            return
        }

        if (registration == null) {
            val owner = store.ownerId.value
            if (owner.isNotBlank()) {
                owners.bind(ChannelPeer(TelegramChannel.ID, owner, ""))
            }
            registration = gateway.start(channel)
        }

        if (pollJob?.isActive != true) {
            _state.value = TelegramConnectionState.Connecting
            pollJob = scope.launch { pollingLoop() }
        }
    }

    @Synchronized
    fun stop() {
        pollJob?.cancel()
        pollJob = null
        registration?.close()
        registration = null
        _state.value = if (!store.isConfigured()) TelegramConnectionState.NotConfigured else TelegramConnectionState.Off
    }

    fun ensureRunning() {
        if (store.enabled.value && store.isConfigured()) {
            sync()
        }
    }

    private suspend fun pollingLoop() {
        while (store.enabled.value && store.isConfigured()) {
            try {
                _state.value = TelegramConnectionState.Connected(store.botUsername.value)
                channel.pollOnce()
                delay(1000)
            } catch (e: CancellationException) {
                break
            } catch (t: Throwable) {
                Log.w("TelegramRuntime", "Polling loop error: ${t.message}")
                _state.value = TelegramConnectionState.Failed(t.message ?: "Connection error")
                delay(5000)
            }
        }
    }
}
