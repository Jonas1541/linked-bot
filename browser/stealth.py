import random
import time
import asyncio
from typing import Tuple

def get_random_delay(min_ms: int = 100, max_ms: int = 300) -> float:
    """Returns a random delay in seconds."""
    return random.randint(min_ms, max_ms) / 1000.0

async def random_sleep(min_sec: float = 1.0, max_sec: float = 3.0):
    """Sleeps asynchronously for a random duration."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

def type_like_human_delay() -> float:
    """Returns the delay for human-like typing speed."""
    # 70% of the time type fast, 30% a bit slower (simulating finding keys)
    if random.random() > 0.3:
        return random.uniform(0.05, 0.15)
    return random.uniform(0.15, 0.4)

async def human_type(page, selector: str, text: str):
    """Types into an input field with varied delays imitating human behavior."""
    await page.click(selector)
    await random_sleep(0.5, 1.5) # Look at the field before typing
    for char in text:
        await page.type(selector, char, delay=type_like_human_delay() * 1000)
    await random_sleep(0.5, 1.0)
