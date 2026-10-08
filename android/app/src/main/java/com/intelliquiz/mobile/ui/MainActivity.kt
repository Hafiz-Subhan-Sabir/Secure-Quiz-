package com.intelliquiz.mobile.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
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
import java.net.InetAddress

/**
 * Phone camera client for IntelliQuiz exams.
 *
 * Desktop QR encodes https://LAN:8767/phone?... — scan, trust local cert in WebView,
 * connect Desktop WSS bridge, keep this app open during the exam.
 */
class MainActivity : AppCompatActivity() {
    private var webView: WebView? = null
    private var statusView: TextView? = null
    private var pendingUrl: String? = null
    private var bridge: DesktopBridge? = null
    private val envMonitor = EnvironmentalMonitor()
    private var examCameraActive = false
    private var lastAppSwitchReportAt = 0L
    private var envWatchStarted = false
    private val envWatchHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val envWatchRunnable = object : Runnable {
        override fun run() {
            if (examCameraActive && envMonitor.paired) {
                reportEnvAnomalyIfNeeded()
            }
            if (envWatchStarted) {
                envWatchHandler.postDelayed(this, 2500L)
            }
        }
    }

    private fun startEnvWatch() {
        if (envWatchStarted) return
        envWatchStarted = true
        envWatchHandler.postDelayed(envWatchRunnable, 2500L)
    }

    private fun stopEnvWatch() {
        envWatchStarted = false
        envWatchHandler.removeCallbacks(envWatchRunnable)
    }

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val url = pendingUrl
        if (granted && url != null) {
            openCameraWebView(url)
        } else {
            showInstructions("Camera permission is required. Tap Allow, then scan again.")
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
            showInstructions("Could not read that QR. Use the QR shown on the exam PC screen.")
            return@registerForActivityResult
        }
        connectBridge(payload)
        ensureCameraThenOpen(payload.toMobileCameraUrl())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
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

    override fun onPause() {
        super.onPause()
        if (examCameraActive && envMonitor.paired) {
            reportPhoneAppSwitch()
        }
    }

    override fun onResume() {
        super.onResume()
        if (examCameraActive && envMonitor.paired) {
            val alive = JSONObject()
                .put("type", "camera_alive")
                .put("source", "android_native")
            try {
                bridge?.send(alive.toString())
            } catch (_: Exception) {
                /* ignore */
            }
            reportEnvAnomalyIfNeeded()
        }
    }

    private fun reportEnvAnomalyIfNeeded() {
        if (!envMonitor.paired) return
        val hint = envMonitor.consumeAnomaly() ?: return
        val plain = when (hint) {
            "covered_or_away" ->
                "Phone camera looks covered or pointing away."
            "sudden_move" ->
                "Phone camera moved suddenly during the exam."
            else -> "Phone room camera warning."
        }
        val payload = JSONObject()
            .put("type", "env_anomaly")
            .put("severity", 0.82)
            .put("gesture_label", "PHONE_MOTION")
            .put("plain_language", plain)
            .put("source", "android_native")
        try {
            bridge?.send(payload.toString())
            setStatus(plain)
        } catch (_: Exception) {
            /* ignore */
        }
    }

    private fun reportPhoneAppSwitch() {
        val now = System.currentTimeMillis()
        if (now - lastAppSwitchReportAt < 8_000L) return
        lastAppSwitchReportAt = now
        val payload = JSONObject()
            .put("type", "env_anomaly")
            .put("severity", 0.92)
            .put("gesture_label", "PHONE_APP_SWITCH")
            .put(
                "plain_language",
                "Student left the IntelliQuiz phone camera app and opened another app. " +
                    "Flagged as a cheating attempt — phone snapshot and PC screen saved for admin.",
            )
            .put("source", "android_native")
        try {
            bridge?.send(payload.toString())
        } catch (_: Exception) {
            /* ignore */
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
        examCameraActive = false
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
            setPadding(0, 32, 0, 48)
        }
        val scanBtn = Button(this).apply {
            text = getString(R.string.scan_qr)
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
                runOnUiThread {
                    envMonitor.start(this@MainActivity)
                    setStatus("Linked to exam PC — keep this screen open")
                    startEnvWatch()
                }
            },
            onMessage = { msg ->
                if (msg.contains("pair_ok") || msg.contains("\"paired\"")) {
                    runOnUiThread {
                        envMonitor.markPaired()
                        setStatus("Paired ✓ — leave this app open during the exam")
                    }
                } else if (msg.contains("pair_fail")) {
                    runOnUiThread {
                        setStatus("Pairing failed — scan the QR again from the PC")
                    }
                }
            },
            onClose = { _, reason ->
                envMonitor.stop()
                runOnUiThread {
                    setStatus("Connection lost — reconnecting… ${reason.take(40)}")
                }
            },
            onError = { ex ->
                envMonitor.stop()
                runOnUiThread {
                    setStatus("Cannot reach exam PC. Same Wi‑Fi? ${ex.message ?: ""}")
                }
            },
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
        examCameraActive = true
        val root = FrameLayout(this)
        val wv = WebView(this)
        webView = wv
        val settings: WebSettings = wv.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

        val status = TextView(this).apply {
            text = "Opening exam camera…"
            setTextColor(Color.WHITE)
            setBackgroundColor(0xCC0A1612.toInt())
            setPadding(28, 24, 28, 24)
            textSize = 14f
            gravity = Gravity.CENTER
        }
        statusView = status

        wv.webViewClient = object : WebViewClient() {
            override fun onReceivedSslError(
                view: WebView?,
                handler: SslErrorHandler?,
                error: SslError?,
            ) {
                // Desktop exam uses a self-signed LAN certificate. Accept only private LAN hosts.
                val host = try {
                    Uri.parse(view?.url ?: url).host.orEmpty()
                } catch (_: Exception) {
                    ""
                }
                if (isPrivateLanHost(host)) {
                    setStatus("Trusted exam PC certificate — loading camera…")
                    handler?.proceed()
                } else {
                    handler?.cancel()
                    setStatus("Blocked unsafe certificate. Scan the QR from your exam PC.")
                    showInstructions("Unsafe link. Scan only the QR shown on the exam computer.")
                }
            }

            override fun onPageFinished(view: WebView?, loadedUrl: String?) {
                setStatus("Camera page loaded — tap Allow if asked, wait for Paired")
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request?.isForMainFrame == true) {
                    setStatus(
                        "Cannot open exam page. Same Wi‑Fi as PC? " +
                            (error?.description?.toString() ?: ""),
                    )
                }
            }
        }
        wv.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.grant(request.resources)
            }
        }

        root.addView(
            wv,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        root.addView(
            status,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM,
            ),
        )
        setContentView(root)
        wv.loadUrl(url)
    }

    private fun setStatus(text: String) {
        statusView?.text = text
    }

    private fun isPrivateLanHost(host: String): Boolean {
        if (host.isBlank()) return false
        return try {
            val addr = InetAddress.getByName(host)
            addr.isSiteLocalAddress || addr.isLoopbackAddress || addr.isLinkLocalAddress
        } catch (_: Exception) {
            host.startsWith("192.168.") ||
                host.startsWith("10.") ||
                host.startsWith("172.") ||
                host == "localhost"
        }
    }

    override fun onDestroy() {
        examCameraActive = false
        stopEnvWatch()
        envMonitor.stop()
        bridge?.close()
        bridge = null
        webView?.destroy()
        webView = null
        statusView = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_PHONE_URL = "phone_url"
    }
}
