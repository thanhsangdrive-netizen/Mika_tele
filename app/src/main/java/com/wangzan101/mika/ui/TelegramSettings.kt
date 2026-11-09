package com.wangzan101.mika.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.wangzan101.mika.R
import com.wangzan101.mika.telegram.TelegramConnectionState
import com.wangzan101.mika.telegram.TelegramRuntime
import com.wangzan101.mika.ui.components.GroupCard
import com.wangzan101.mika.ui.components.GroupLabel
import com.wangzan101.mika.ui.components.ListRow
import com.wangzan101.mika.ui.components.MikaSwitch
import com.wangzan101.mika.ui.components.PageScaffold
import com.wangzan101.mika.ui.components.PillTone
import com.wangzan101.mika.ui.components.StatusPill
import com.wangzan101.mika.ui.theme.MikaIcons
import com.wangzan101.mika.ui.theme.MikaTheme
import com.wangzan101.mika.ui.theme.MikaType
import kotlinx.coroutines.launch

@Composable
internal fun TelegramEntryStatus(state: TelegramConnectionState, enabled: Boolean) {
    val (text, tone) = when (state) {
        is TelegramConnectionState.Connected -> "@${state.username}" to PillTone.Ok
        is TelegramConnectionState.Connecting -> "Đang kết nối" to PillTone.Accent
        is TelegramConnectionState.Failed -> "Lỗi kết nối" to PillTone.Warn
        TelegramConnectionState.NotConfigured -> "Chưa cấu hình" to PillTone.Neutral
        TelegramConnectionState.Off -> (if (enabled) "Đang bật" else "Chưa bật") to PillTone.Neutral
    }
    StatusPill(text, tone)
}

@Composable
fun TelegramSettingsScreen(
    runtime: TelegramRuntime,
    onBack: () -> Unit,
) {
    val store = runtime.store
    val enabled by store.enabled.collectAsState()
    val token by store.botToken.collectAsState()
    val ownerId by store.ownerId.collectAsState()
    val username by store.botUsername.collectAsState()
    val state by runtime.state.collectAsState()

    var inputToken by remember(token) { mutableStateOf(token) }
    var inputOwner by remember(ownerId) { mutableStateOf(ownerId) }
    var showToken by remember { mutableStateOf(false) }
    var testing by remember { mutableStateOf(false) }
    var statusMessage by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    PageScaffold(title = "Telegram Bot", onBack = onBack) {
        GroupLabel("Trạng thái")
        GroupCard {
            ListRow(
                icon = MikaIcons.Message,
                title = "Kích hoạt Telegram Bot",
                subtitle = when (val s = state) {
                    is TelegramConnectionState.Connected -> "Đã kết nối: @${s.username.ifBlank { username }}"
                    is TelegramConnectionState.Connecting -> "Đang kết nối..."
                    is TelegramConnectionState.Failed -> "Lỗi: ${s.reason}"
                    TelegramConnectionState.NotConfigured -> "Chưa điền Bot Token"
                    TelegramConnectionState.Off -> "Đang tắt"
                },
                first = true,
                onClick = {
                    val next = !enabled
                    store.setEnabled(next)
                    if (next) runtime.sync() else runtime.stop()
                }
            ) {
                MikaSwitch(
                    checked = enabled,
                    onCheckedChange = { next ->
                        store.setEnabled(next)
                        if (next) runtime.sync() else runtime.stop()
                    }
                )
            }
        }

        GroupLabel("Cấu hình Bot")
        GroupCard {
            Column(modifier = Modifier.padding(16.dp)) {
                OutlinedTextField(
                    value = inputToken,
                    onValueChange = { inputToken = it.trim() },
                    label = { Text("Telegram Bot Token") },
                    placeholder = { Text("Ví dụ: 123456789:ABCdefGHI...") },
                    singleLine = true,
                    visualTransformation = if (showToken) VisualTransformation.None else PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = inputOwner,
                    onValueChange = { inputOwner = it.trim() },
                    label = { Text("Telegram User ID (Chủ sở hữu)") },
                    placeholder = { Text("Tùy chọn: để trống để tự nhận diện lần đầu") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(16.dp))

                Button(
                    onClick = {
                        testing = true
                        statusMessage = "Đang kiểm tra kết nối tới Telegram..."
                        scope.launch {
                            val result = runtime.testAndSave(inputToken, inputOwner)
                            testing = false
                            statusMessage = if (result.isSuccess) {
                                "✅ Kết nối thành công tới @${result.getOrNull()}!"
                            } else {
                                "❌ Thất bại: ${result.exceptionOrNull()?.message}"
                            }
                        }
                    },
                    enabled = inputToken.isNotBlank() && !testing,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (testing) "Đang kiểm tra..." else "Lưu & Kiểm tra kết nối")
                }

                statusMessage?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = it,
                        style = MikaType.Caption,
                        color = if (it.startsWith("✅")) MikaTheme.colors.ok else MikaTheme.colors.bad
                    )
                }
            }
        }

        GroupLabel("Hướng dẫn nhanh")
        GroupCard {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "1. Mở Telegram và nhắn tin với @BotFather để tạo một bot mới (lệnh /newbot) và nhận Token.\n" +
                            "2. Dán mã Bot Token vào ô trên rồi bấm \"Lưu & Kiểm tra kết nối\".\n" +
                            "3. Bật công tắc kích hoạt ở trên.\n" +
                            "4. Mở bot của bạn trên Telegram và gửi bất kỳ yêu cầu nào (ví dụ: \"Đặt báo thức 7h sáng mai\"), Mika sẽ tự động thực hiện và gửi kết quả về Telegram cho bạn!",
                    style = MikaType.Caption,
                    color = MikaTheme.colors.ink2
                )
            }
        }
    }
}
