package com.intelliquiz.mobile.pairing

import org.json.JSONObject
import java.net.URLEncoder

/**
 * Mirrors contracts/schemas/pairing.qr.v1.json
 * Also understands Desktop HTTPS phone QR URLs.
 */
data class PairingPayload(
    val schema: String,
    val sessionId: String,
    val pairingToken: String,
    val desktopEndpoint: String,
    val expiresAt: String,
    val examCode: String? = null,
    val mobileCameraUrl: String? = null,
) {
    fun toMobileCameraUrl(): String {
        mobileCameraUrl?.takeIf { it.startsWith("https://") }?.let { return it }
        val sid = URLEncoder.encode(sessionId, "UTF-8")
        val tok = URLEncoder.encode(pairingToken, "UTF-8")
        val ws = URLEncoder.encode(desktopEndpoint, "UTF-8")
        val base = desktopEndpoint
            .substringBefore("/ws/pair")
            .replace("wss://", "https://")
            .replace("ws://", "http://")
        return "$base/phone?session_id=$sid&pairing_token=$tok&ws=$ws"
    }

    companion object {
        const val SCHEMA = "pairing.qr.v1"

        fun fromJsonMap(map: Map<String, Any?>): PairingPayload {
            require(map["schema"] == SCHEMA) { "Unsupported pairing schema" }
            return PairingPayload(
                schema = SCHEMA,
                sessionId = map["session_id"] as String,
                pairingToken = map["pairing_token"] as String,
                desktopEndpoint = map["desktop_endpoint"] as String,
                expiresAt = map["expires_at"] as String,
                examCode = map["exam_code"] as String?,
                mobileCameraUrl = map["mobile_camera_url"] as String?,
            )
        }

        fun tryParseQrText(raw: String): PairingPayload? {
            val text = raw.trim()
            if (text.startsWith("https://") && text.contains("/phone")) {
                val uri = android.net.Uri.parse(text)
                val sid = uri.getQueryParameter("session_id") ?: return null
                val tok = uri.getQueryParameter("pairing_token") ?: return null
                val ws = uri.getQueryParameter("ws") ?: return null
                return PairingPayload(
                    schema = SCHEMA,
                    sessionId = sid,
                    pairingToken = tok,
                    desktopEndpoint = ws,
                    expiresAt = "",
                    mobileCameraUrl = text,
                )
            }
            if (!text.startsWith("{")) return null
            return try {
                val obj = JSONObject(text)
                if (obj.optString("schema") != SCHEMA) return null
                PairingPayload(
                    schema = SCHEMA,
                    sessionId = obj.getString("session_id"),
                    pairingToken = obj.getString("pairing_token"),
                    desktopEndpoint = obj.getString("desktop_endpoint"),
                    expiresAt = obj.optString("expires_at"),
                    examCode = obj.optString("exam_code").ifBlank { null },
                    mobileCameraUrl = obj.optString("mobile_camera_url").ifBlank { null },
                )
            } catch (_: Exception) {
                null
            }
        }
    }
}
