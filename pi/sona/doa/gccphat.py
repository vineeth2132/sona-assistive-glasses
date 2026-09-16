"""GCC-PHAT direction of arrival from raw multichannel USB capture.

Written for the XVF3800 flashed with Seeed's 16 kHz 6-channel USB firmware: USB
channels 3-6 carry the four raw microphones (channels 1-2 are the processed outputs).
Bench-check on the hat before trusting the angles.

Why this exists: the XVF3800's on-chip DoA is tuned for *speech*. For the demo we
also want to localize sirens/horns — GCC-PHAT tracks any dominant sound source.
"""

import asyncio
import logging

import numpy as np
import sounddevice as sd

from .. import config

log = logging.getLogger(__name__)

SPEED_OF_SOUND = 343.0
# XVF3800 geometry per AEC_MIC_ARRAY_GEO: 66 mm square, order mic0..mic3 (x, y in metres);
# verify board axes vs. the wearer's front on the hat (python -m sona.doa.xvf_usb prints it).
MIC_POS = np.array([[+0.033, -0.033], [+0.033, +0.033], [-0.033, +0.033], [-0.033, -0.033]])
PAIRS = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2), (1, 3)]


def gcc_phat(a: np.ndarray, b: np.ndarray, fs: int, max_tau: float) -> float:
    n = len(a) + len(b)
    A = np.fft.rfft(a, n=n)
    B = np.fft.rfft(b, n=n)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-12
    cc = np.fft.irfft(R, n=n)
    max_shift = max(1, int(fs * max_tau))
    cc = np.concatenate([cc[-max_shift:], cc[: max_shift + 1]])
    return (int(np.argmax(np.abs(cc))) - max_shift) / fs


class GccPhatDoa:
    def __init__(
        self,
        hub,
        device: int | str | None = None,
        fs: int = 16000,
        block: int = 2048,
        energy_gate: float = 1e-5,
    ):
        self.hub = hub
        self.device = device
        self.fs = fs
        self.block = block
        self.energy_gate = energy_gate
        # precompute predicted pair delays for a 2° grid
        thetas = np.deg2rad(np.arange(0, 360, 2))
        u = np.stack([np.sin(thetas), np.cos(thetas)], axis=1)  # 0° = front (+y), cw
        proj = MIC_POS @ u.T  # (4, n_theta)
        self.grid_deg = np.arange(0, 360, 2)
        self.pred = np.stack(
            [-(proj[i] - proj[j]) / SPEED_OF_SOUND for i, j in PAIRS]
        )  # (n_pairs, n_theta)
        self.max_taus = [
            float(np.linalg.norm(MIC_POS[i] - MIC_POS[j]) / SPEED_OF_SOUND) for i, j in PAIRS
        ]

    async def run(self):
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=8)

        def enqueue(data):
            if not q.full():
                q.put_nowait(data)

        def cb(indata, frames, t, status):
            loop.call_soon_threadsafe(enqueue, indata.copy())

        with sd.InputStream(
            device=self.device,
            channels=6,
            samplerate=self.fs,
            blocksize=self.block,
            dtype="float32",
            callback=cb,
        ):
            log.info("GCC-PHAT DoA running (6ch USB, raw mics on ch3-6 @ %d Hz)", self.fs)
            while True:
                x = (await q.get())[:, config.XVF_RAW_MIC_CHANNELS]  # (block, 4) raw mics
                if float(np.mean(x**2)) < self.energy_gate:
                    self.hub.publish("doa", {"angle": None, "active": False, "speech": None})
                    continue
                taus = np.array(
                    [
                        gcc_phat(x[:, i], x[:, j], self.fs, self.max_taus[k])
                        for k, (i, j) in enumerate(PAIRS)
                    ]
                )
                cost = np.sum((self.pred - taus[:, None]) ** 2, axis=0)
                theta = float(self.grid_deg[int(np.argmin(cost))])
                angle = (theta + config.AZIMUTH_OFFSET_DEG) % 360
                self.hub.publish(
                    "doa", {"angle": angle, "active": True, "speech": None, "moved": True}
                )
