import os

from config import OUTPUT_DIR, STATE_DIR


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)
