package com.intelliquiz.mobile.camera

/**
 * CameraX environmental monitor placeholder.
 * Captures side/rear frames and emits lightweight anomaly signals to Desktop.
 */
class EnvironmentalMonitor {
    @Volatile
    var running: Boolean = false
        private set

    fun start() {
        running = true
    }

    fun stop() {
        running = false
    }
}
