package com.wangzan101.mika.cap.phone.display

import android.graphics.Bitmap
import kotlinx.coroutines.flow.StateFlow

/**
 * 抽象展示端口：支持背景虚拟屏（AgentDisplay）或设备主屏幕（MainAgentDisplay）。
 */
interface AgentDisplayPort {
    val displayId: Int
    val width: Int
    val height: Int
    val frames: StateFlow<Bitmap?>
    fun latestFramePng(): ByteArray?
    fun lastFrameAt(): Long?
    fun latestFrameBitmap(): Bitmap?
    fun release()
}
