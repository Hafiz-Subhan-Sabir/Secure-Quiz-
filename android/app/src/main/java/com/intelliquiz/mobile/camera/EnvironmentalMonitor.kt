package com.intelliquiz.mobile.camera

import android.Manifest
import android.content.pm.PackageManager
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.abs

/**
 * Rear-camera room monitor: samples brightness / motion so the app can flag
 * covered lenses or sudden phone moves while paired.
 */
class EnvironmentalMonitor {
    @Volatile
    var running: Boolean = false
        private set

    @Volatile
    var paired: Boolean = false
        private set

    /** 0..1 rough motion score from recent frames. */
    @Volatile
    var motionScore: Float = 0f
        private set

    /** Average luminance 0..255. */
    @Volatile
    var brightness: Float = 128f
        private set

    @Volatile
    var anomalyHint: String? = null
        private set

    private var activity: AppCompatActivity? = null
    private val executor = Executors.newSingleThreadExecutor()
    private var lastLuma: Float? = null
    private val lastAnomalyAt = AtomicLong(0L)

    fun start(host: AppCompatActivity) {
        if (running) return
        activity = host
        if (ContextCompat.checkSelfPermission(host, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        running = true
        val providerFuture = ProcessCameraProvider.getInstance(host)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build()
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(executor) { image ->
                try {
                    val plane = image.planes.firstOrNull()?.buffer ?: return@setAnalyzer
                    var sum = 0L
                    var n = 0
                    val step = 16
                    var i = 0
                    while (i < plane.limit()) {
                        sum += (plane.get(i).toInt() and 0xFF)
                        n++
                        i += step
                    }
                    if (n == 0) return@setAnalyzer
                    val avg = sum.toFloat() / n
                    brightness = avg
                    val prev = lastLuma
                    if (prev != null) {
                        val delta = abs(avg - prev)
                        motionScore = (delta / 40f).coerceIn(0f, 1f)
                        val now = System.currentTimeMillis()
                        if (now - lastAnomalyAt.get() > 8_000L) {
                            when {
                                avg < 18f || avg > 245f -> {
                                    lastAnomalyAt.set(now)
                                    anomalyHint = "covered_or_away"
                                }
                                delta > 28f -> {
                                    lastAnomalyAt.set(now)
                                    anomalyHint = "sudden_move"
                                }
                                else -> anomalyHint = null
                            }
                        }
                    }
                    lastLuma = avg
                } finally {
                    image.close()
                }
            }
            try {
                provider.unbindAll()
                provider.bindToLifecycle(
                    host,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    analysis,
                )
            } catch (_: Exception) {
                running = false
            }
        }, ContextCompat.getMainExecutor(host))
    }

    fun markPaired() {
        paired = true
    }

    fun consumeAnomaly(): String? {
        val hint = anomalyHint
        anomalyHint = null
        return hint
    }

    fun stop() {
        running = false
        paired = false
        anomalyHint = null
        activity?.let { act ->
            try {
                ProcessCameraProvider.getInstance(act).get().unbindAll()
            } catch (_: Exception) {
                /* ignore */
            }
        }
        activity = null
    }
}
