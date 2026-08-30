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

/**
 * CameraX environmental monitor — rear camera preview + lightweight motion sampling.
 * Emits heartbeat signals to Desktop when paired.
 */
class EnvironmentalMonitor {
    @Volatile
    var running: Boolean = false
        private set

    @Volatile
    var paired: Boolean = false
        private set

    private var activity: AppCompatActivity? = null
    private val executor = Executors.newSingleThreadExecutor()

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
                image.close()
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

    fun stop() {
        running = false
        paired = false
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
