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
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.intelliquiz.mobile.R
import com.intelliquiz.mobile.pairing.PairingPayload

/**
 * Phone camera client for IntelliQuiz exams.
 *
 * Desktop QR encodes https://LAN:8767/phone?... — this activity opens it in a
 * camera-capable WebView so pairing + room frames work end-to-end.
 */
class MainActivity : AppCompatActivity() {
    private var webView: WebView? = null
    private var pendingUrl: String? = null

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = resolvePhoneUrl(intent)
        if (url != null) {
            ensureCameraThenOpen(url)
            return
        }
        showInstructions(null)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        resolvePhoneUrl(intent)?.let { ensureCameraThenOpen(it) }
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
        root.addView(title)
        root.addView(body)
        setContentView(root)
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
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_PHONE_URL = "phone_url"
    }
}
