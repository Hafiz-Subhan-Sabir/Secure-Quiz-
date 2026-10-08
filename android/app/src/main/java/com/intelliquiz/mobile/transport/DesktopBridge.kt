package com.intelliquiz.mobile.transport

import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Bridge to Desktop local WSS endpoint from the QR payload.
 * Exam PC uses a self-signed LAN cert — we trust it only for that connection.
 */
class DesktopBridge(
    private val endpoint: String,
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

    fun connect() {
        if (endpointIsWss(endpoint)) {
            try {
                client.setSocketFactory(trustLocalExamSslFactory())
            } catch (_: Exception) {
                /* fall through — connect may still fail and surface via onError */
            }
        }
        client.connect()
    }

    fun send(text: String) {
        if (client.isOpen) client.send(text)
    }

    fun close() {
        try {
            client.close()
        } catch (_: Exception) {
            /* ignore */
        }
    }

    companion object {
        private fun endpointIsWss(endpoint: String): Boolean =
            endpoint.trim().lowercase().startsWith("wss://")

        private fun trustLocalExamSslFactory(): SSLSocketFactory {
            val trustAll = object : X509TrustManager {
                override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }
            val ctx = SSLContext.getInstance("TLS")
            ctx.init(null, arrayOf<TrustManager>(trustAll), SecureRandom())
            return ctx.socketFactory
        }
    }
}
