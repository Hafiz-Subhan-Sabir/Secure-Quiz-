# IntelliQuiz Android (Secondary Camera)

Pairs with the Student Desktop app via QR (`pairing.qr.v1`) and streams environmental monitoring signals.

Open `android/` in Android Studio (Giraffe+ / AGP 8.7).

## Modules (source)

| Package | Role |
|---------|------|
| `pairing` | QR payload parse |
| `transport` | WebSocket bridge to Desktop |
| `camera` | CameraX environmental monitor |
| `ui` | MainActivity / scan flow |

Does **not** own exam answers — Desktop remains source of truth.
