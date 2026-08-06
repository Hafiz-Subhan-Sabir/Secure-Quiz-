"""FaceGest gesture labels and IntelliQuiz proctoring risk mapping.

Class abbreviations follow FaceGest (CVPRW 2025) Table 2 / Table 4 order:
SBR SBL MO LP DB S N RE F SH B&S RE&MO W&HT
"""

from __future__ import annotations

GESTURE_CLASSES: dict[int, dict[str, str]] = {
    0: {
        "abbr": "SBR",
        "name": "single_blink_right",
        "category": "eye",
        "description": "Close and open right eye quickly",
    },
    1: {
        "abbr": "SBL",
        "name": "single_blink_left",
        "category": "eye",
        "description": "Close and open left eye quickly",
    },
    2: {
        "abbr": "MO",
        "name": "mouth_open",
        "category": "mouth",
        "description": "Open mouth wide",
    },
    3: {
        "abbr": "LP",
        "name": "lips_pursed",
        "category": "mouth",
        "description": "Press lips together tightly",
    },
    4: {
        "abbr": "DB",
        "name": "double_blink",
        "category": "eye",
        "description": "Blink both eyes twice quickly",
    },
    5: {
        "abbr": "S",
        "name": "smile",
        "category": "mouth",
        "description": "Stretch lips in a smile",
    },
    6: {
        "abbr": "N",
        "name": "nod",
        "category": "head",
        "description": "Move head up and down (nod)",
    },
    7: {
        "abbr": "RE",
        "name": "raise_eyebrows",
        "category": "eye",
        "description": "Raise both eyebrows",
    },
    8: {
        "abbr": "F",
        "name": "frown",
        "category": "mouth",
        "description": "Draw eyebrows together, wrinkling forehead",
    },
    9: {
        "abbr": "SH",
        "name": "head_shake",
        "category": "head",
        "description": "Move head side to side (shake)",
    },
    10: {
        "abbr": "B&S",
        "name": "blink_and_smile",
        "category": "combined",
        "description": "Blink while smiling",
    },
    11: {
        "abbr": "RE&MO",
        "name": "raise_eyebrows_mouth_open",
        "category": "combined",
        "description": "Raise eyebrows while opening mouth",
    },
    12: {
        "abbr": "W&HT",
        "name": "wink_and_head_tilt",
        "category": "combined",
        "description": "Wink one eye and tilt head",
    },
}

# Heuristic risk weights for exam integrity (0 = benign, 1 = highly suspicious).
# These feed the Cheating Probability Score later; tune with admin strictness settings.
PROCTORING_RISK: dict[int, float] = {
    0: 0.15,  # blink right — normal
    1: 0.15,  # blink left — normal
    2: 0.55,  # mouth open — possible talking
    3: 0.35,  # pursed lips — mild
    4: 0.20,  # double blink — mostly normal
    5: 0.10,  # smile — benign
    6: 0.70,  # nod — gaze/head movement
    7: 0.25,  # raise eyebrows — mild
    8: 0.20,  # frown — mild
    9: 0.85,  # head shake — looking around
    10: 0.30,  # blink + smile
    11: 0.60,  # brows + mouth open
    12: 0.90,  # wink + head tilt — high gaze diversion
}

CLASS_NAMES: list[str] = [GESTURE_CLASSES[i]["abbr"] for i in range(len(GESTURE_CLASSES))]


def risk_for_label(label: int) -> float:
    return float(PROCTORING_RISK.get(int(label), 0.5))


def display_name(label: int) -> str:
    meta = GESTURE_CLASSES.get(int(label))
    if not meta:
        return str(label)
    return f"{meta['abbr']} ({meta['name']})"
