"""What you tell Soundscape about its calls, and how that changes the next ones.

Each answer counts for one kind of sound at one microphone: "vehicle at Backyard" is
separate from "vehicle at Front". Every "wrong" lowers confidence for that pair by
15 %, every "right" raises it by 5 %, never below 40 % or above 115 %. Counts, not a
running value, are kept, so changing an answer or resetting is exact and the effect
of each answer is easy to read back.
"""
from __future__ import annotations

import time

WRONG_STEP = 0.85
RIGHT_STEP = 1.05
LOWEST, HIGHEST = 0.4, 1.15
ANSWERS_KEPT = 1000
FAR = ""            # sounds placed overhead or by ADS-B, at no one microphone


def pair(cls: str, mic: str | None) -> str:
    return f"{cls}|{mic or FAR}"


class Calibration:
    def __init__(self, data: dict | None = None) -> None:
        data = data or {}
        self.counts: dict[str, dict[str, int]] = {
            k: {"right": int(v.get("right", 0)), "wrong": int(v.get("wrong", 0))}
            for k, v in (data.get("counts") or {}).items()}
        self.answers: dict[str, dict] = dict(data.get("answers") or {})

    def factor(self, cls: str, mic: str | None) -> float:
        c = self.counts.get(pair(cls, mic))
        if not c:
            return 1.0
        return max(LOWEST, min(HIGHEST, WRONG_STEP ** c["wrong"] * RIGHT_STEP ** c["right"]))

    def _count(self, key: str, field: str, step: int) -> None:
        c = self.counts.setdefault(key, {"right": 0, "wrong": 0})
        c[field] = max(0, c[field] + step)
        if not c["right"] and not c["wrong"]:
            del self.counts[key]

    def _apply(self, answer: dict, step: int) -> None:
        if answer["verdict"] == "right":
            self._count(pair(answer["cls"], answer["mic"]), "right", step)
            return
        self._count(pair(answer["cls"], answer["mic"]), "wrong", step)
        actual = answer.get("actual")
        if actual and actual != answer["cls"]:
            self._count(pair(actual, answer["mic"]), "right", step)

    def answer(self, event_id: int, cls: str, mic: str | None, verdict: str | None,
               actual: str | None = None, label: str = "") -> dict | None:
        """Record (or change, or with verdict None withdraw) the answer for one sound."""
        key = str(event_id)
        if old := self.answers.pop(key, None):
            self._apply(old, -1)
        if verdict is None:
            return None
        new = {"cls": cls, "mic": mic, "verdict": verdict, "actual": actual if verdict == "wrong" else None,
               "label": label, "at": round(time.time())}
        self._apply(new, +1)
        self.answers[key] = new
        while len(self.answers) > ANSWERS_KEPT:
            # forget the oldest answer's text, but not what it taught
            self.answers.pop(next(iter(self.answers)))
        return new

    def reset(self, cls: str | None = None, mic: str | None = None) -> None:
        """Forget what was learnt: everything, or one kind, or one kind at one microphone."""
        def hit(k: str) -> bool:
            c, m = k.split("|", 1)
            return (cls is None or c == cls) and (mic is None or m == (mic or FAR))
        for k in [k for k in self.counts if hit(k)]:
            del self.counts[k]
        for k in [k for k, a in self.answers.items() if hit(pair(a["cls"], a["mic"]))]:
            del self.answers[k]

    def summary(self) -> list[dict]:
        out = []
        for k, c in sorted(self.counts.items()):
            cls, mic = k.split("|", 1)
            f = self.factor(cls, mic or None)
            out.append({"cls": cls, "mic": mic or None, "right": c["right"], "wrong": c["wrong"],
                        "factor": round(f, 2)})
        return out

    def as_dict(self) -> dict:
        return {"counts": self.counts, "answers": self.answers}
