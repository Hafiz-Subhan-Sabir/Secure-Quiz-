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
    onOpen: () -> Unit = {},
    onMessage: (String) -> Unit = {},
    onClose: (code: Int, reason: String) -> Unit = { _, _ -> },
    onError: (Exception) -> Unit = {},
) {
    private val openHandler: () -> Unit = onOpen
    private val messageHandler: (String) -> Unit = onMessage
    private val closeHandler: (code: Int, reason: String) -> Unit = onClose
    private val errorHandler: (Exception) -> Unit = onError

    private val client = object : WebSocketClient(URI(endpoint)) {
        override fun onOpen(handshakedata: ServerHandshake?) {
            openHandler()
        }

        override fun onMessage(message: String) {
            messageHandler(message)
        }

        override fun onClose(code: Int, reason: String, remote: Boolean) {
            closeHandler(code, reason)
        }

        override fun onError(ex: Exception) {
            errorHandler(ex)
        }
    }

    fun connect() = client.connect()
    fun send(text: String) = client.send(text)
    fun close() = client.close()
}
