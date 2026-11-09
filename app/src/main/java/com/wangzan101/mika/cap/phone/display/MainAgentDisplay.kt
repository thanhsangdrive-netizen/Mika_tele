package com.wangzan101.mika.cap.phone.display

import android.graphics.Bitmap
import android.os.SystemClock
import android.view.Display
import com.wangzan101.mika.cap.phone.a11y.ScreenAccessibility
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.runBlocking
import java.io.ByteArrayOutputStream

/**
 * 直接使用主屏幕（DEFAULT_DISPLAY）的展示端口。
 * 用于在前台直接操作真实屏幕，无需创建背景虚拟屏。
 */
class MainAgentDisplay(
    private val a11y: ScreenAccessibility,
    override val width: Int,
    override val height: Int,
) : AgentDisplayPort {
    override val displayId: Int get() = Display.DEFAULT_DISPLAY

    private val _frames = MutableStateFlow<Bitmap?>(null)
    override val frames: StateFlow<Bitmap?> = _frames.asStateFlow()

    @Volatile private var lastTimestamp = 0L

    override fun latestFrameBitmap(): Bitmap? {
        val shot = runBlocking { a11y.takeMainScreenshot() }
        if (shot is ScreenAccessibility.MainShot.Ok) {
            lastTimestamp = System.nanoTime()
            val bmp = shot.bitmap
            _frames.value = bmp
            return bmp
        }
        return null
    }

    override fun latestFramePng(): ByteArray? {
        val bmp = latestFrameBitmap() ?: return null
        return try {
            ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
        } finally {
            bmp.recycle()
        }
    }

    override fun lastFrameAt(): Long? = lastTimestamp.takeIf { it > 0 }

    override fun release() {
        _frames.value = null
    }
}
