package com.intelliquiz.mobile.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.zxing.integration.android.IntentIntegrator
import com.intelliquiz.mobile.R
import com.intelliquiz.mobile.camera.EnvironmentalMonitor
import com.intelliquiz.mobile.pairing.PairingPayload
import com.intelliquiz.mobile.transport.DesktopBridge
import org.json.JSONObject

/**
 * Phone camera client for IntelliQuiz exams.
 *
 * Desktop QR encodes https://LAN:8767/phone?... — scan or open deep link,
 * connect Desktop WS bridge, then load the phone camera WebView.
 */
class MainActivity : AppCompatActivity() {
    private var webView: WebView? = null
    private var pendingUrl: String? = null
    private var bridge: DesktopBridge? = null
    private val envMonitor = EnvironmentalMonitor()

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val url = pendingUrl
        if (granted && url != null) {
            openCameraWebView(url)
        } else {
            showInstructions("Camera permission is required for exam proctoring.")
        }
    }

    private val qrScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val scan = IntentIntegrator.parseActivityResult(result.resultCode, result.data)
        val raw = scan?.contents?.trim().orEmpty()
        if (raw.isEmpty()) {
            showInstructions(null)
            return@registerForActivityResult
        }
        val payload = PairingPayload.tryParseQrText(raw)
        if (payload == null) {
            showInstructions("Could not read that QR code. Scan the code shown on your desktop exam screen.")
            return@registerForActivityResult
        }
        connectBridge(payload)
        ensureCameraThenOpen(payload.toMobileCameraUrl())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = resolvePhoneUrl(intent)
        if (url != null) {
            PairingPayload.tryParseQrText(url)?.let { connectBridge(it) }
            ensureCameraThenOpen(url)
            return
        }
        showInstructions(null)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        resolvePhoneUrl(intent)?.let { url ->
            PairingPayload.tryParseQrText(url)?.let { connectBridge(it) }
            ensureCameraThenOpen(url)
        }
    }

    private fun ensureCameraThenOpen(url: String) {
        pendingUrl = url
        val granted = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        if (granted) {
            openCameraWebView(url)
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun showInstructions(extra: String?) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
            setBackgroundColor(0xFF0A1612.toInt())
        }
        val title = TextView(this).apply {
            text = getString(R.string.app_name)
            setTextColor(0xFF2EC4A0.toInt())
            textSize = 22f
        }
        val body = TextView(this).apply {
            text = buildString {
                append(getString(R.string.scan_instructions))
                if (!extra.isNullOrBlank()) {
                    append("\n\n")
                    append(extra)
                }
            }
            setTextColor(0xFFE8EEF4.toInt())
            textSize = 16f
            setPadding(0, 32, 0, 0)
        }
        val scanBtn = Button(this).apply {
            text = getString(R.string.scan_qr)
            setPadding(0, 48, 0, 0)
            setOnClickListener { launchQrScan() }
        }
        root.addView(title)
        root.addView(body)
        root.addView(scanBtn)
        setContentView(root)
    }

    private fun launchQrScan() {
        val integrator = IntentIntegrator(this)
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
        integrator.setPrompt(getString(R.string.scan_prompt))
        integrator.setBeepEnabled(false)
        integrator.setOrientationLocked(true)
        qrScanLauncher.launch(integrator.createScanIntent())
    }

    private fun connectBridge(payload: PairingPayload) {
        bridge?.close()
        val endpoint = payload.desktopEndpoint
        bridge = DesktopBridge(
            endpoint = endpoint,
            onOpen = {
                val hello = JSONObject()
                    .put("type", "pair")
                    .put("session_id", payload.sessionId)
                    .put("pairing_token", payload.pairingToken)
                    .put("source", "android_native")
                bridge?.send(hello.toString())
                runOnUiThread { envMonitor.start(this@MainActivity) }
            },
            onMessage = { msg ->
                if (msg.contains("paired")) {
                    runOnUiThread { envMonitor.markPaired() }
                }
            },
            onClose = { _, _ -> envMonitor.stop() },
            onError = { _ -> envMonitor.stop() },
        )
        bridge?.connect()
    }

    private fun resolvePhoneUrl(intent: Intent?): String? {
        if (intent == null) return null
        val data: Uri? = intent.data
        if (data != null) {
            val asText = data.toString()
            if (asText.contains("/phone")) return asText
        }
        val extra = intent.getStringExtra(EXTRA_PHONE_URL)
        if (!extra.isNullOrBlank() && extra.startsWith("https://")) return extra

        val shared = intent.getStringExtra(Intent.EXTRA_TEXT)
        if (!shared.isNullOrBlank()) {
            PairingPayload.tryParseQrText(shared)?.let { return it.toMobileCameraUrl() }
            if (shared.startsWith("https://") && shared.contains("/phone")) return shared.trim()
        }
        return null
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun openCameraWebView(url: String) {
        val wv = WebView(this)
        webView = wv
        val settings: WebSettings = wv.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        wv.webViewClient = WebViewClient()
        wv.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.grant(request.resources)
            }
        }
        setContentView(wv)
        wv.loadUrl(url)
    }

    override fun onDestroy() {
        envMonitor.stop()
        bridge?.close()
        bridge = null
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_PHONE_URL = "phone_url"
    }
}
