"""Reading the machine's vitals aloud, whether or not they were read.

One function, reached from the `system_monitor` skill when the router picks the
`stark_diagnostics` action: sample CPU, RAM, battery and GPU, then narrate them
in the sarcastic Hinglish register the rest of JARVIS speaks in.

The narration is the problem. When psutil is not installed the except branch
substitutes 12.5% CPU, 45.2% RAM, 85% battery and mains power, and the sentence
that follows presents them exactly as it presents measured ones -- "diagnostics
sweep complete ho gaya hai" over four numbers nothing sampled. A machine with no
battery gets 100% and "charging par hai" by the same route. Both are in the
tests as pinned defects rather than fixed, because that is a separate commit.

This file holds both halves of the `system_monitor` skill. The router picks
between them by action: `stark_diagnostics` gets the four-vital narration below,
anything else gets `system_vitals`, which reads two of the same numbers and says
them plainly. They were split across two files until now, which is why the same
`import psutil` appears twice.

Two of the four places in the tree that read these vitals are therefore here. The
other two are ProactiveMonitor._check_performance and ._check_hardware, which read
them on a timer to alert on thresholds rather than to answer a question. Unifying
all four is not a move and so cannot be gated the way `stark_diagnostics` was; the
sites are named here so whoever does it can find them.
"""
from loguru import logger


def stark_diagnostics() -> str:
    """Runs system hardware checks and formats them into a witty, sarcastic Hinglish MCU diagnostic briefing."""
    logger.info("Executing Stark diagnostic sweep...")
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        bat_percent = battery.percent if battery else 100
        power_plugged = battery.power_plugged if battery else True
    except ImportError:
        cpu, ram, bat_percent, power_plugged = 12.5, 45.2, 85, True

    gpu_info = ""
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_info = f"GPU load {gpus[0].load*100:.1f}% hai aur temperature {gpus[0].temperature}°C."
    except Exception:
        pass

    bat_status = "charging par hai" if power_plugged else "battery par chal raha hai"
    response = (
        f"Sir, diagnostics sweep complete ho gaya hai. [laugh] Main arc reactor—sorry, "
        f"aapke laptop ki battery check kar chuki hu, ye abhi {bat_percent}% par hai aur {bat_status}. "
        f"CPU utilization {cpu}% hai aur memory load {ram}% par chal raha hai. "
        f"{gpu_info} Overall, coding system bilkul active aur nominal hai, sir!"
    )
    return response


def system_vitals() -> str:
    """CPU and RAM, said plainly, for any `system_monitor` action but the sweep.

    Two differences from `stark_diagnostics` above, both worth knowing:

    It reports the numbers it actually read, and when psutil is missing it says
    so instead of inventing them. That makes this the honest one of the pair.

    But `except ImportError` is all it catches, and psutil raises other things --
    AccessDenied on a locked-down Windows box, or OSError when a counter is
    unavailable. Those propagate out of here and out of the whole command
    dispatch, so an unreadable sensor takes down the turn rather than the answer.
    Pinned in the tests as it stands; widening it is a separate commit.
    """
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        return f"System resources are nominal. CPU is at {cpu} percent and RAM is at {ram} percent, sir."
    except ImportError:
        return "psutil is not installed. Run `pip install psutil` to monitor the system."
