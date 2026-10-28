"""Hiệu ứng âm thanh: file thật trong assets/sfx/, âm tạo bằng code làm dự phòng.

Đặt một file mang tên sự kiện vào assets/sfx/ để thay âm thanh của nó:

    roll    khối lăn một bước
    switch  công tắc bật/tắt cầu
    split   khối tách thành hai khối nhỏ (công tắc tách)
    fall    khối rơi khỏi bàn
    win     khối chìm vào ô đích

Định dạng hỗ trợ: .wav, .ogg, .mp3 (xét theo thứ tự đó). Thiếu file thì dùng
một âm ngắn tạo bằng code, nên game luôn có âm thanh.
"""
from __future__ import annotations

import logging
import math
from array import array
from pathlib import Path

import pygame

from src.gui.theme import ASSETS_DIR

SFX_DIR = ASSETS_DIR / 'sfx'
EVENTS = ('roll', 'switch', 'split', 'fall', 'win')
FORMATS = ('.wav', '.ogg', '.mp3')

# Âm dự phòng: danh sách (Hz đầu, Hz cuối, giây). Nhiều phần tử thì phát lần lượt
# (nhạc thắng). Cao độ trượt tuyến tính từ đầu tới cuối.
TONES = {
    'roll':   [(220, 160, 0.07)],                      # tiếng thịch trầm, ngắn
    'switch': [(880, 880, 0.06), (1320, 1320, 0.06)],  # tiếng click hai nốt
    'split':  [(400, 1200, 0.18)],                     # tiếng vút đi lên
    'fall':   [(700, 120, 0.45)],                      # tiếng huýt dài đi xuống
    'win':    [(523, 523, 0.11), (659, 659, 0.11), (784, 784, 0.22)],  # C-E-G
}


def _tone(parts, rate: int, channels: int, loudness: int = 5000) -> pygame.mixer.Sound:
    """Tạo âm sóng sin, nhỏ dần ở cuối mỗi nốt."""
    samples = array('h')
    phase = 0.0
    for start_hz, end_hz, seconds in parts:
        count = max(1, int(rate * seconds))
        for i in range(count):
            hz = start_hz + (end_hz - start_hz) * i / count
            phase += 2 * math.pi * hz / rate
            envelope = min(1.0, i / (rate * 0.005)) * (1 - i / count)  # to dần 5 ms, rồi nhỏ dần
            samples.extend([int(loudness * envelope * math.sin(phase))] * channels)
    return pygame.mixer.Sound(buffer=samples)


class SoundBank:
    """Mỗi sự kiện một Sound. Chỉ tạo sau khi pygame.mixer đã khởi tạo."""

    def __init__(self, folder: Path = SFX_DIR, volume: float = 0.6):
        rate, _, channels = pygame.mixer.get_init()
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        for name in EVENTS:
            path = next((folder / f'{name}{ext}' for ext in FORMATS
                         if (folder / f'{name}{ext}').exists()), None)
            sound = None
            if path is not None:
                try:
                    sound = pygame.mixer.Sound(str(path))
                except pygame.error as error:  # file không đọc được: giữ âm tạo bằng code
                    logging.getLogger(__name__).warning('SFX: cannot load %s: %s', path.name, error)
            self.sounds[name] = sound or _tone(TONES[name], rate, channels)
        self.set_volume(volume)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        for sound in self.sounds.values():
            sound.set_volume(self.volume)

    def play(self, name: str = 'roll', volume: float = 1.0) -> None:
        """volume (0..1) chỉnh âm lượng cho lần phát này, ví dụ cho các lần nảy nhẹ hơn."""
        sound = self.sounds.get(name)
        if sound is not None:
            channel = sound.play()
            if channel is not None:
                channel.set_volume(volume)
