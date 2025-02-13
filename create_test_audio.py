import numpy as np
from scipy.io import wavfile
import subprocess
import os

# Generate a 5 second sine wave at 440 Hz
sample_rate = 44100
duration = 5
t = np.linspace(0, duration, int(sample_rate * duration))
audio = np.sin(2 * np.pi * 440 * t)

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Save as WAV file first
wav_file = 'temp_audio.wav'
wavfile.write(wav_file, sample_rate, audio.astype(np.float32))

# Convert to m4a using ffmpeg
output_file = 'data/short-classroom-sample.m4a'
subprocess.run(['ffmpeg', '-i', wav_file, '-c:a',
               'aac', '-b:a', '192k', output_file])

# Clean up temporary WAV file
os.remove(wav_file)
