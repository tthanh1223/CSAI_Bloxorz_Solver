"""Sound effects: real files from assets/sfx/, generated tones as fallback.

Drop a file named after the event into assets/sfx/ to replace its sound:

    roll    the block rolls one step
    switch  a switch toggles a bridge
    split   the block splits into two cubes (split switch)
    fall    the block falls off the board
    win     the block sinks into the goal

Accepted formats: .wav, .ogg, .mp3 (checked in that order). A missing file
falls back to a short tone generated in code, so the game always has sound.
"""
from __future__ import annotations

import math
from array import array
from pathlib import Path

import pygame

SFX_DIR = Path(__file__).resolve().parents[2] / 'assets' / 'sfx'
EVENTS = ('roll', 'switch', 'split', 'fall', 'win')
FORMATS = ('.wav', '.ogg', '.mp3')

# Fallback tones: list of (start Hz, end Hz, seconds). Several entries play one
# after another (the win jingle). Pitch glides linearly from start to end.
TONES = {
    'roll':   [(220, 160, 0.07)],                      # short low thud
    'switch': [(880, 880, 0.06), (1320, 1320, 0.06)],  # two-note click
    'split':  [(400, 1200, 0.18)],                     # rising whoosh
    'fall':   [(700, 120, 0.45)],                      # long falling whistle
    'win':    [(523, 523, 0.11), (659, 659, 0.11), (784, 784, 0.22)],  # C-E-G
}


def _tone(parts, rate: int, channels: int, loudness: int = 5000) -> pygame.mixer.Sound:
    """Build a sine-wave sound that fades out at the end of each note."""
    samples = array('h')
    phase = 0.0
    for start_hz, end_hz, seconds in parts:
        count = max(1, int(rate * seconds))
        for i in range(count):
            hz = start_hz + (end_hz - start_hz) * i / count
            phase += 2 * math.pi * hz / rate
            envelope = min(1.0, i / (rate * 0.005)) * (1 - i / count)  # 5 ms fade-in, fade-out
            samples.extend([int(loudness * envelope * math.sin(phase))] * channels)
    return pygame.mixer.Sound(buffer=samples)


class SoundBank:
    """One Sound per event. Create only after pygame.mixer is initialised."""

    def __init__(self, folder: Path = SFX_DIR, volume: float = 0.6):
        rate, _, channels = pygame.mixer.get_init()
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.from_file: set[str] = set()
        for name in EVENTS:
            path = next((folder / f'{name}{ext}' for ext in FORMATS
                         if (folder / f'{name}{ext}').exists()), None)
            sound = None
            if path is not None:
                try:
                    sound = pygame.mixer.Sound(str(path))
                    self.from_file.add(name)
                except pygame.error as error:  # unreadable file: keep the tone
                    print(f'SFX: cannot load {path.name}: {error}')
            self.sounds[name] = sound or _tone(TONES[name], rate, channels)
        self.set_volume(volume)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        for sound in self.sounds.values():
            sound.set_volume(self.volume)

    def play(self, name: str = 'roll') -> None:
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()
