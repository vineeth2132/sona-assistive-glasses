"""Which YAMNet sounds get shown on the glasses — editable at runtime from the mirror.

Each entry groups one or more AudioSet classes under a display label (e.g. SIREN =
"Siren" + "Civil defense siren" + "Police car (siren)" ...). Only enabled entries reach
the classifier. Anything from YAMNet's 521 classes can be added live.
"""

import csv

from .. import config


def load_class_names() -> list[str]:
    try:
        with open(config.YAMNET_CLASS_MAP) as f:
            return [r["display_name"] for r in csv.DictReader(f)]
    except OSError:
        return []


def label_for(class_name: str) -> str:
    """'Vehicle horn, car horn, honking' -> 'VEHICLE HORN'."""
    head = class_name.split(",")[0].split("(")[0].strip()
    return head.upper()[:12]


class SoundWatchlist:
    def __init__(self, class_names: list[str] | None = None):
        self.class_names = class_names if class_names is not None else load_class_names()
        self._entries: dict[str, dict] = {}
        for key, (label, prio, thr) in config.SOUND_TARGETS.items():
            e = self._entries.setdefault(
                label,
                {
                    "label": label,
                    "classes": [],
                    "priority": prio,
                    "threshold": thr,
                    "enabled": label in config.SOUND_ENABLED_DEFAULT,
                },
            )
            for name in self.class_names:
                if key in name.lower() and name not in e["classes"]:
                    e["classes"].append(name)
            e["priority"] = max(e["priority"], prio)
            e["threshold"] = min(e["threshold"], thr)

    def entries(self) -> list[dict]:
        return [dict(e, classes=list(e["classes"])) for e in self._entries.values()]

    def toggle(self, label: str, enabled: bool) -> bool:
        if label not in self._entries:
            return False
        self._entries[label]["enabled"] = bool(enabled)
        return True

    def add(self, class_name: str, label: str | None = None) -> bool:
        if class_name not in self.class_names:
            return False
        label = (label or label_for(class_name)).upper()[:12]
        e = self._entries.setdefault(
            label,
            {
                "label": label,
                "classes": [],
                "priority": 1,
                "threshold": config.SOUND_DEFAULT_THRESHOLD,
                "enabled": True,
            },
        )
        if class_name not in e["classes"]:
            e["classes"].append(class_name)
        e["enabled"] = True
        return True

    def remove(self, label: str) -> bool:
        return self._entries.pop(label, None) is not None

    def restore(self, entries: list[dict]) -> None:
        """Apply a saved list: enabled flags, custom additions, and removals of defaults."""
        if not entries:
            return
        keep: set[str] = set()
        for e in entries:
            label = str(e.get("label", "")).upper()[:12]
            if not label:
                continue
            cur = self._entries.get(label)
            if cur is None:
                classes = [c for c in e.get("classes", []) if c in self.class_names]
                if not classes:
                    continue
                cur = self._entries[label] = {
                    "label": label,
                    "classes": classes,
                    "priority": int(e.get("priority", 1)),
                    "threshold": float(e.get("threshold", config.SOUND_DEFAULT_THRESHOLD)),
                    "enabled": True,
                }
            cur["enabled"] = bool(e.get("enabled", cur["enabled"]))
            keep.add(label)
        for label in list(self._entries):
            if label not in keep:
                del self._entries[label]
