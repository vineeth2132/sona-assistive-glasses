"""Mock DoA source for development without the mic array.

The mirror web UI publishes 'doa' directly when you click/drag its compass, so the
relay mode has nothing to do; sweep mode rotates the angle automatically (nice for
screen recordings).
"""

import asyncio


class MockDoa:
    def __init__(self, hub, sweep: bool = False, deg_per_s: float = 40.0):
        self.hub = hub
        self.sweep = sweep
        self.deg_per_s = deg_per_s

    async def run(self):
        if not self.sweep:
            return  # web UI drives the angle
        angle = 0.0
        while True:
            self.hub.publish(
                "doa", {"angle": angle % 360, "active": True, "speech": False, "moved": True}
            )
            angle += self.deg_per_s * 0.1
            await asyncio.sleep(0.1)
