from __future__ import annotations

import re

URDU_SCRIPT = re.compile(r"[\u0600-\u06FF]")

ROMAN_HINTS = {
    "aap",
    "batao",
    "bataen",
    "chhutti",
    "chutti",
    "chuttian",
    "hai",
    "hain",
    "hoti",
    "hota",
    "kaise",
    "kese",
    "kitna",
    "kitne",
    "kitni",
    "kya",
    "kyun",
    "mera",
    "mere",
    "mujhe",
    "mujhy",
    "nahi",
    "nahin",
    "pas",
    "paas",
}


def detect_reply_style(question: str) -> str:
    if URDU_SCRIPT.search(question or ""):
        return "urdu"
    tokens = set(re.findall(r"[a-zA-Z']+", (question or "").lower()))
    if len(tokens.intersection(ROMAN_HINTS)) >= 2:
        return "roman_urdu"
    return "english"


def language_instruction(question: str) -> str:
    style = detect_reply_style(question)
    if style == "urdu":
        return "The employee wrote in Urdu script. Reply in Urdu script only."
    if style == "roman_urdu":
        return (
            "The employee wrote in Roman Urdu (Latin letters). "
            "Reply in Roman Urdu only. Do not use Urdu script. Do not switch to formal English."
        )
    return "The employee wrote in English. Reply in English only. Do not use Urdu script or Roman Urdu."
