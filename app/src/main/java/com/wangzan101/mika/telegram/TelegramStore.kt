package com.wangzan101.mika.telegram

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class TelegramStore(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _enabled = MutableStateFlow(prefs.getBoolean(KEY_ENABLED, false))
    val enabled: StateFlow<Boolean> = _enabled.asStateFlow()

    private val _botToken = MutableStateFlow(prefs.getString(KEY_BOT_TOKEN, "").orEmpty())
    val botToken: StateFlow<String> = _botToken.asStateFlow()

    private val _ownerId = MutableStateFlow(prefs.getString(KEY_OWNER_ID, "").orEmpty())
    val ownerId: StateFlow<String> = _ownerId.asStateFlow()

    private val _botUsername = MutableStateFlow(prefs.getString(KEY_BOT_USERNAME, "").orEmpty())
    val botUsername: StateFlow<String> = _botUsername.asStateFlow()

    var lastUpdateId: Long
        get() = prefs.getLong(KEY_LAST_UPDATE_ID, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_UPDATE_ID, value).apply()

    fun setEnabled(on: Boolean) {
        prefs.edit().putBoolean(KEY_ENABLED, on).apply()
        _enabled.value = on
    }

    fun saveConfig(token: String, owner: String, username: String = "") {
        prefs.edit()
            .putString(KEY_BOT_TOKEN, token.trim())
            .putString(KEY_OWNER_ID, owner.trim())
            .putString(KEY_BOT_USERNAME, username.trim())
            .apply()
        _botToken.value = token.trim()
        _ownerId.value = owner.trim()
        _botUsername.value = username.trim()
    }

    fun setOwnerId(owner: String) {
        prefs.edit().putString(KEY_OWNER_ID, owner.trim()).apply()
        _ownerId.value = owner.trim()
    }

    fun setBotUsername(username: String) {
        prefs.edit().putString(KEY_BOT_USERNAME, username.trim()).apply()
        _botUsername.value = username.trim()
    }

    fun isConfigured(): Boolean = _botToken.value.isNotBlank()

    companion object {
        private const val PREFS_NAME = "mika_telegram_prefs"
        private const val KEY_ENABLED = "telegram_enabled"
        private const val KEY_BOT_TOKEN = "telegram_bot_token"
        private const val KEY_OWNER_ID = "telegram_owner_id"
        private const val KEY_BOT_USERNAME = "telegram_bot_username"
        private const val KEY_LAST_UPDATE_ID = "telegram_last_update_id"
    }
}
