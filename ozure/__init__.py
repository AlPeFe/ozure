"""Ozure — Fujifilm custom recipe manager over USB PTP.

The USB/PTP layer mirrors the protocol implemented in fuji-ptp-core
(https://github.com/AlPeFe/fuji-ptp-core): same operations, same property
block, same wire conversions. Keeping the two in sync matters more than
sharing code, since the core is Rust and this skill runs anywhere Python runs.
"""

__version__ = "0.2.2"
