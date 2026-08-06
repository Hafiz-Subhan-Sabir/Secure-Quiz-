package com.intelliquiz.mobile.pairing

/**
 * Mirrors contracts/schemas/pairing.qr.v1.json
 */
data class PairingPayload(
    val schema: String,
    val sessionId: String,
    val pairingToken: String,
    val desktopEndpoint: String,
    val expiresAt: String,
    val examCode: String? = null,
) {
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
            )
        }
    }
}
