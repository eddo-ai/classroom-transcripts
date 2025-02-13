import numpy as np
from scipy.io import wavfile
import os


def generate_test_audio():
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Generate a 5-second sine wave at 440 Hz
    duration = 5  # seconds
    sample_rate = 44100
    t = np.linspace(0, duration, duration * sample_rate)
    audio_data = np.sin(2 * np.pi * 440 * t)

    # Save as WAV file
    output_path = "data/short-classroom-sample.wav"
    wavfile.write(output_path, sample_rate, audio_data.astype(np.float32))
    print(f"Generated test audio file: {output_path}")


if __name__ == "__main__":
    generate_test_audio()
