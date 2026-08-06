package com.intelliquiz.mobile.transport

import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI

/**
 * Lightweight bridge to Desktop local WS endpoint from QR payload.
 * Production: add token handshake + binary frame protocol versioning.
 */
class DesktopBridge(
    endpoint: String,
    private val onOpen: () -> Unit = {},
    private val onMessage: (String) -> Unit = {},
    private val onClose: (code: Int, reason: String) -> Unit = { _, _ -> },
    private val onError: (Exception) -> Unit = {},
) {
    private val client = object : WebSocketClient(URI(endpoint)) {
        override fun onOpen(handshakedata: ServerHandshake?) = onOpen()
        override fun onMessage(message: String) = onMessage(message)
        override fun onClose(code: Int, reason: String, remote: Boolean) = onClose(code, reason)
        override fun onError(ex: Exception) = onError(ex)
    }

    fun connect() = client.connect()
    fun send(text: String) = client.send(text)
    fun close() = client.close()
}
