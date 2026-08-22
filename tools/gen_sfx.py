"""Writes the placeholder cues into `assets/sfx/`.

The sound is generated, never committed, for the two reasons `tools/gen_art.py`
gives about the art: nothing binary goes in the repo, and no amount of
not-being-a-sound-designer blocks the code. Replacing this with real audio means
dropping in WAVs with the same filenames -- the game loads cues by name and does
not care what is in them.

    python tools/gen_sfx.py

Unlike `gen_art.py` this imports no pygame and needs no SDL at all: a WAV is a
header and a list of samples, and the standard library writes both. So there is
no dependency here beyond Python itself, and nothing to set up before running it.

Every voice is short -- 70 to 600ms -- and enveloped to silence at both ends. A
sample that starts or stops on a non-zero value clicks, and a click on every
swing is worse than the silence this is replacing.
"""

from __future__ import annotations

import array
import math
import random
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402

RATE = config.SOUND_RATE

# Fixed seed, for the reason gen_art.py fixes its own: the noise in these is
# texture, but a build that produces a different WAV every run makes "did the
# audio change?" unanswerable.
RNG = random.Random(20260822)

#: Peak amplitude of a single cue, as a fraction of full scale. Well under 1.0
#: on purpose -- a dozen of these can be playing at once in a crowded arena, and
#: mixing several cues that each peak at full scale is how a fight turns into
#: clipping.
PEAK = 0.42


# --- building blocks ---------------------------------------------------------
def _count(seconds: float) -> int:
    return int(RATE * seconds)


def noise(seconds: float) -> list[float]:
    """White noise. The body of every impact in here."""
    return [RNG.uniform(-1.0, 1.0) for _ in range(_count(seconds))]


def sweep(seconds: float, f0: float, f1: float, shape: str = "sine") -> list[float]:
    """A tone gliding from `f0` to `f1`.

    Phase is accumulated rather than computed from `t * frequency`, which is the
    one thing worth being careful about here: the naive form glides the whole
    waveform rather than its frequency and comes out as a warble.
    """
    count = _count(seconds)
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        t = i / count if count else 0.0
        freq = f0 + (f1 - f0) * t
        phase += 2.0 * math.pi * freq / RATE
        if shape == "square":
            out.append(1.0 if math.sin(phase) >= 0.0 else -1.0)
        elif shape == "triangle":
            out.append(2.0 / math.pi * math.asin(max(-1.0, min(1.0, math.sin(phase)))))
        else:
            out.append(math.sin(phase))
    return out


def tone(seconds: float, freq: float, shape: str = "sine") -> list[float]:
    return sweep(seconds, freq, freq, shape)


def lowpass(source: list[float], k: float) -> list[float]:
    """One-pole filter. Takes the fizz off white noise so it reads as a thump."""
    out: list[float] = []
    previous = 0.0
    for value in source:
        previous += k * (value - previous)
        out.append(previous)
    return out


def envelope(
    source: list[float], attack: float = 0.01, curve: float = 2.0
) -> list[float]:
    """Fade in over `attack` of the length, then decay to nothing.

    The decay is a power curve rather than a straight line: a linear fade on a
    percussive sound is audible as a sound being switched off partway through.
    """
    count = len(source)
    if not count:
        return []
    rise = max(1, int(count * attack))
    out: list[float] = []
    for i, value in enumerate(source):
        if i < rise:
            gain_at = i / rise
        else:
            gain_at = (1.0 - (i - rise) / max(1, count - rise)) ** curve
        out.append(value * gain_at)
    return out


def layer(*parts: list[float]) -> list[float]:
    """Sum voices of unequal length, keeping the longest."""
    longest = max((len(part) for part in parts), default=0)
    out = [0.0] * longest
    for part in parts:
        for i, value in enumerate(part):
            out[i] += value
    return out


def gain(source: list[float], amount: float) -> list[float]:
    return [value * amount for value in source]


def sequence(*parts: list[float]) -> list[float]:
    """Play voices one after another, for the arpeggios."""
    out: list[float] = []
    for part in parts:
        out.extend(part)
    return out


# --- the voices --------------------------------------------------------------
# One per name in config.SOUND_NAMES. Each returns floats in roughly [-1, 1];
# `write` normalises and clamps, so a voice that comes back a little hot is
# scaled rather than clipped.
def voice_swing() -> list[float]:
    # Filtered noise with no tone under it: a swing that misses moves air and
    # hits nothing.
    return envelope(lowpass(noise(0.10), 0.28), attack=0.06, curve=2.4)


def voice_shoot() -> list[float]:
    return layer(
        envelope(lowpass(noise(0.07), 0.55), attack=0.02, curve=3.0),
        gain(envelope(sweep(0.07, 900, 320), attack=0.02, curve=3.0), 0.5),
    )


def voice_dodge() -> list[float]:
    # Lower and longer than a swing, and quieter -- it happens constantly, and a
    # roll that announces itself becomes the loudest thing in a fight.
    return gain(envelope(lowpass(noise(0.14), 0.16), attack=0.12, curve=2.0), 0.7)


def voice_buff() -> list[float]:
    return gain(
        sequence(
            envelope(tone(0.07, 523, "triangle"), attack=0.05, curve=1.6),
            envelope(tone(0.07, 659, "triangle"), attack=0.05, curve=1.6),
            envelope(tone(0.13, 784, "triangle"), attack=0.05, curve=1.6),
        ),
        0.75,
    )


def voice_hit() -> list[float]:
    # The one that matters most: a noise transient for the contact and a short
    # low sweep under it for the weight. This is the cue the whole feel layer has
    # been missing -- hitstop and screenshake are already firing beside it.
    return layer(
        envelope(lowpass(noise(0.11), 0.45), attack=0.01, curve=3.0),
        gain(envelope(sweep(0.11, 190, 65), attack=0.01, curve=2.4), 0.9),
    )


def voice_hurt() -> list[float]:
    # Deliberately unlike `hit`: lower, longer, rougher. "Was that me?" has to be
    # answerable without looking at the health bar.
    return layer(
        envelope(lowpass(noise(0.20), 0.22), attack=0.01, curve=2.2),
        gain(envelope(sweep(0.20, 150, 48, "triangle"), attack=0.01, curve=2.0), 1.0),
    )


def voice_crit() -> list[float]:
    # Bright and rising, and it plays *over* its hit rather than instead of it --
    # the CRIT event accompanies the HIT for the same reason.
    return gain(
        envelope(sweep(0.13, 620, 1180, "square"), attack=0.03, curve=2.6), 0.55
    )


def voice_blocked() -> list[float]:
    # Two close tones, which is what reads as metallic without a filter bank.
    return gain(
        layer(
            envelope(tone(0.09, 1150), attack=0.02, curve=3.2),
            gain(envelope(tone(0.09, 1490), attack=0.02, curve=3.2), 0.6),
        ),
        0.6,
    )


def voice_death() -> list[float]:
    return layer(
        gain(envelope(lowpass(noise(0.30), 0.20), attack=0.02, curve=1.8), 0.7),
        envelope(sweep(0.30, 300, 70, "triangle"), attack=0.02, curve=1.6),
    )


def voice_hero_death() -> list[float]:
    # The longest thing in here. It plays once per run, at the moment the run
    # ends, and it is the only cue allowed to take its time.
    return layer(
        gain(envelope(lowpass(noise(0.60), 0.12), attack=0.03, curve=1.4), 0.5),
        envelope(sweep(0.60, 220, 40, "triangle"), attack=0.03, curve=1.3),
    )


def voice_trap() -> list[float]:
    # Sharper than `hurt` and with a mid tone in it, so being burned by the floor
    # is distinguishable from being hit by a body. The events are separate for
    # exactly this reason -- see the note on TRAP in game/events.py.
    return layer(
        envelope(lowpass(noise(0.16), 0.70), attack=0.01, curve=2.8),
        gain(envelope(sweep(0.16, 420, 180, "square"), attack=0.01, curve=2.6), 0.45),
    )


def voice_prop() -> list[float]:
    # A door taken or a fixture used. Soft, and the only cue in the game that is
    # not about violence.
    return gain(
        sequence(
            envelope(tone(0.09, 587), attack=0.06, curve=1.5),
            envelope(tone(0.13, 880), attack=0.06, curve=1.5),
        ),
        0.6,
    )


def voice_coin() -> list[float]:
    # Two square notes a fourth apart, rising. This is the oldest sound in games
    # and it is recognisable precisely because nobody has improved on it.
    return gain(
        sequence(
            envelope(tone(0.05, 988, "square"), attack=0.04, curve=2.0),
            envelope(tone(0.09, 1319, "square"), attack=0.04, curve=2.0),
        ),
        0.4,
    )


def voice_relic() -> list[float]:
    # Three notes rather than the coin's two, and triangle rather than square: a
    # relic and a coin are both pickups, and the only thing that tells them apart
    # on screen is the colour of a number.
    return gain(
        sequence(
            envelope(tone(0.07, 784, "triangle"), attack=0.05, curve=1.6),
            envelope(tone(0.07, 1047, "triangle"), attack=0.05, curve=1.6),
            envelope(tone(0.14, 1319, "triangle"), attack=0.05, curve=1.6),
        ),
        0.55,
    )


#: One entry per name in `config.SOUND_NAMES`, checked in `main`. The same shape
#: as `gen_art.PAINTERS` and for the same reason: adding a cue is a name in
#: config.py and a voice here, and forgetting either half fails loudly.
VOICES = {
    "swing": voice_swing,
    "shoot": voice_shoot,
    "dodge": voice_dodge,
    "buff": voice_buff,
    "hit": voice_hit,
    "hurt": voice_hurt,
    "crit": voice_crit,
    "blocked": voice_blocked,
    "death": voice_death,
    "hero_death": voice_hero_death,
    "trap": voice_trap,
    "prop": voice_prop,
    "coin": voice_coin,
    "relic": voice_relic,
}


# --- writing -----------------------------------------------------------------
def write(path: Path, source: list[float]) -> None:
    """Normalise to PEAK, clamp, and write 16-bit mono PCM."""
    loudest = max((abs(value) for value in source), default=0.0)
    scale = (PEAK / loudest) if loudest > 0.0 else 0.0

    samples = array.array("h")
    for value in source:
        samples.append(max(-32768, min(32767, int(value * scale * 32767))))

    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.tobytes())


def main() -> int:
    missing = [name for name in config.SOUND_NAMES if name not in VOICES]
    if missing:
        print(f"no voice for: {', '.join(missing)}", file=sys.stderr)
        return 1

    config.SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    total = 0.0
    for name in config.SOUND_NAMES:
        source = VOICES[name]()
        write(config.SOUNDS_DIR / f"{name}.wav", source)
        total += len(source) / RATE

    print(
        f"wrote {config.SOUNDS_DIR.relative_to(ROOT)}  "
        f"({len(config.SOUND_NAMES)} cues, {total:.1f}s at {RATE}Hz mono)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
