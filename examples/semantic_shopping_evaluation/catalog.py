# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""SYNTHETIC test catalog and a deterministic keyword retriever (no real merchant, no personal data)."""

from __future__ import annotations

import re

DOCS: dict[str, str] = {
    "kettle": "Aster electric kettle (TEST STORE). Price Rs 1,999. Capacity 1.2 litre. Stainless steel body. Auto shut-off. Stock: 14 units. Warranty: 12 months.",
    "blender": "Brio blender 600W (TEST STORE). Price Rs 3,450. Two jars: 1.5 litre and 0.3 litre. Colours: black only. Stock: 0 units (out of stock). Warranty: 24 months.",
    "toaster": "Crisp 2-slice toaster (TEST STORE). Price Rs 1,250. Seven browning levels. Removable crumb tray. Stock: 6 units. Warranty: 6 months.",
    "iron": "Glide steam iron (TEST STORE). Price Rs 2,100. 1800W. Non-stick soleplate. Stock: 9 units. Warranty: 12 months.",
    "cooker": "Pressure cooker 5 litre (TEST STORE). Price Rs 2,799. Induction compatible. Aluminium body. Stock: 3 units. Warranty: 36 months.",
    "returns": "Returns policy (TEST STORE). Unused items can be returned within 7 days of delivery. Opened small appliances are not returnable unless faulty. Refunds go to the original payment method in 5 to 7 working days.",
    "delivery": "Delivery (TEST STORE). Standard delivery takes 3 to 5 working days. Delivery fee is Rs 60 for orders under Rs 999 and free above. Cash on delivery is not available.",
    "offer": "Offer (TEST STORE). Kettle and toaster bundle price Rs 3,000 while stock lasts. Offer valid until 30 November 2026.",
}
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "and",
    "to",
    "for",
    "it",
    "in",
    "on",
    "do",
    "does",
    "what",
    "how",
    "much",
    "can",
    "i",
    "you",
    "me",
    "my",
    "this",
    "that",
    "with",
    "have",
    "has",
    "there",
}


def retrieve(question: str, k: int = 2) -> list[str]:
    """Top-k documents by shared words; documents with no shared word are never returned."""
    words = {w for w in _WORD.findall(question.lower()) if w not in _STOP}
    scored = []
    for name, text in DOCS.items():
        overlap = len(words & set(_WORD.findall(text.lower())))
        if overlap:
            scored.append((overlap, name))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [DOCS[n] for _, n in scored[:k]]
