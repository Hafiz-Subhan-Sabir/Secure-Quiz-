"""Tiny SVG placeholders that stand in for webcam / phone camera evidence frames."""

from __future__ import annotations

import base64


def _svg_data_uri(title: str, subtitle: str, accent: str = "#1f8f78") -> str:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b3d34"/>
      <stop offset="100%" stop-color="#164e5c"/>
    </linearGradient>
  </defs>
  <rect width="640" height="400" fill="url(#g)"/>
  <circle cx="320" cy="150" r="54" fill="none" stroke="{accent}" stroke-width="4"/>
  <ellipse cx="320" cy="250" rx="90" ry="70" fill="none" stroke="{accent}" stroke-width="3" opacity="0.7"/>
  <text x="32" y="48" fill="#f4fffb" font-family="Segoe UI, Arial" font-size="22" font-weight="700">{title}</text>
  <text x="32" y="78" fill="#b7d5cc" font-family="Segoe UI, Arial" font-size="15">{subtitle}</text>
  <text x="32" y="370" fill="#8fb3a8" font-family="Segoe UI, Arial" font-size="13">IntelliQuiz · auto-captured evidence</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


GESTURE_EVIDENCE = {
    "head_shake": _svg_data_uri("Abnormal gesture: Head shake", "Looking side-to-side · primary webcam", "#d4654b"),
    "wink_tilt": _svg_data_uri("Abnormal gesture: Wink + head tilt", "Gaze diverted · primary webcam", "#d4654b"),
    "mouth_open": _svg_data_uri("Possible talking: Mouth open", "Speech risk · primary webcam", "#b86a1c"),
    "android_env": _svg_data_uri("Environment alert", "Secondary Android camera · side view", "#1f8f78"),
    "multi_face": _svg_data_uri("Multiple faces detected", "Second person in frame · primary webcam", "#d4654b"),
}
