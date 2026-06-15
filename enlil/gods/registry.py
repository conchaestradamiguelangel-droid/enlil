from __future__ import annotations

from .base import GodProfile
from .claude import PROFILE as CLAUDE_PROFILE
from .enki import PROFILE as ENKI_PROFILE
from .ninurta import PROFILE as NINURTA_PROFILE
from .inanna import PROFILE as INANNA_PROFILE
from .anu import PROFILE as ANU_PROFILE
from .marduk import PROFILE as MARDUK_PROFILE
from .nabu import PROFILE as NABU_PROFILE
from .nergal import PROFILE as NERGAL_PROFILE
from .tiamat import PROFILE as TIAMAT_PROFILE


# Timeouts per god -- Opus and reasoning models need more time
GOD_TIMEOUTS: dict[str, float] = {
    "claude":  150.0,
    "enki":    200.0,
    "ninurta": 90.0,
    "inanna":  90.0,
    "anu":     120.0,
    "marduk":  130.0,
    "nabu":    400.0,
    "nergal":  200.0,
    "tiamat":  75.0,
}


def build_default_pantheon() -> dict[str, GodProfile]:
    """Build and return the default ENLIL pantheon with all nine god agents."""
    return {
        "claude":  CLAUDE_PROFILE,
        "enki":    ENKI_PROFILE,
        "ninurta": NINURTA_PROFILE,
        "inanna":  INANNA_PROFILE,
        "anu":     ANU_PROFILE,
        "marduk":  MARDUK_PROFILE,
        "nabu":    NABU_PROFILE,
        "nergal":  NERGAL_PROFILE,
        "tiamat":  TIAMAT_PROFILE,
    }
