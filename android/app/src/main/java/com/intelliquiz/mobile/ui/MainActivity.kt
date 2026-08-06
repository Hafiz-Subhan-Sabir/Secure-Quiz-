package com.intelliquiz.mobile.ui

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.intelliquiz.mobile.R

/**
 * Entry UI: QR scan → pair → start environmental camera feed.
 * Wire ZXing scanner + CameraX in the next Android milestone.
 */
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val view = TextView(this).apply {
            text = getString(R.string.app_name) + "\n\n" +
                getString(R.string.scan_qr) + "\n" +
                "Pairs with Desktop via pairing.qr.v1"
            setTextColor(0xFFE8EEF4.toInt())
            textSize = 18f
            setPadding(48, 96, 48, 48)
        }
        setContentView(view)
    }
}
