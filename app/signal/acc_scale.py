"""LIS3DH accelerometer raw bytes → mg conversion."""

from __future__ import annotations


def parse_sample_xyz(data: bytes | bytearray, offset: int) -> tuple[int, int, int]:
    """Parse one 6-byte sample (X_L, X_H, Y_L, Y_H, Z_L, Z_H) as int16 LE.

    LIS3DH ±2g high-resolution: left-aligned 12-bit, >> 4 → mg (1 mg/LSB).
    """
    x = int.from_bytes(data[offset : offset + 2], "little", signed=True) >> 4
    y = int.from_bytes(data[offset + 2 : offset + 4], "little", signed=True) >> 4
    z = int.from_bytes(data[offset + 4 : offset + 6], "little", signed=True) >> 4
    return x, y, z
