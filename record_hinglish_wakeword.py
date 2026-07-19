"""
record_hinglish_wakeword.py
===============================================================================
Interactive script to capture and enroll your voice for Hinglish JARVIS wake words.
It records voice samples of Hinglish wake phrases ("Jarvis", "Hey Jarvis",
"Jarvis bhai", "Sun Jarvis", "Chalo utho Jarvis"), extracts your unique MFCC voice
print, and saves it to config/voice_profile.json for instant identification in main.py.
===============================================================================
"""

import os
import sys
import time
import json
import numpy as np
from loguru import logger

# Ensure root directory is in python path
JARVIS_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, JARVIS_ROOT)

from core.wake_word import compute_mean_mfcc, cosine_similarity

def record_audio_sample(duration_sec: float = 2.5, sample_rate: int = 16000) -> np.ndarray:
    """Records audio from microphone using sounddevice or pyaudio for duration_sec seconds."""
    try:
        import sounddevice as sd
        num_samples = int(duration_sec * sample_rate)
        print("  🎙 Recording... Speak NOW!")
        recording = sd.rec(num_samples, samplerate=sample_rate, channels=1, dtype='float32')
        sd.wait()
        print("  ✓ Recording complete.")
        return recording.flatten()
    except Exception as sd_err:
        logger.debug(f"sounddevice recording failed ({sd_err}). Trying PyAudio fallback...")
        import pyaudio
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True, frames_per_buffer=1024)
        print("  🎙 Recording... Speak NOW!")
        frames = []
        for _ in range(0, int(sample_rate / 1024 * duration_sec)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        print("  ✓ Recording complete.")
        stream.stop_stream()
        stream.close()
        p.terminate()
        raw_bytes = b"".join(frames)
        audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0

def run_voice_enrollment():
    print("\n" + "="*65)
    print("   JARVIS Hinglish Voice Profile Enrollment & Wake Word Setup")
    print("="*65)
    print(" This script will record 5 short voice samples of you saying")
    print(" Hinglish wake words so JARVIS learns your personal voice print.")
    print("=========================================================\n")

    samples = [
        "Sample 1: 'Jarvis'",
        "Sample 2: 'Hey Jarvis'",
        "Sample 3: 'Jarvis bhai'",
        "Sample 4: 'Sun Jarvis'",
        "Sample 5: 'Chalo utho Jarvis'"
    ]

    mfcc_vectors = []
    
    for idx, sample_name in enumerate(samples, 1):
        while True:
            print(f"\n[{idx}/5] Ready to record {sample_name}")
            input("  Press ENTER, then clearly speak the phrase into your mic... ")
            
            audio_np = record_audio_sample(duration_sec=2.2, sample_rate=16000)
            
            # Check for non-silence
            rms = np.sqrt(np.mean(audio_np**2))
            if rms < 0.003:
                print("  ❌ Voice signal too quiet or background silence detected. Please try again.")
                continue
            
            # Extract MFCC
            vec = compute_mean_mfcc(audio_np, sample_rate=16000)
            mfcc_vectors.append(vec)
            print(f"  ✅ Voice sample {idx} captured successfully! (Signal RMS: {rms:.4f})")
            break
            
        time.sleep(0.5)

    # Calculate average voice profile vector
    mean_profile_vector = np.mean(mfcc_vectors, axis=0)

    # Save to config/voice_profile.json
    profile_dir = os.path.abspath("config")
    os.makedirs(profile_dir, exist_ok=True)
    profile_path = os.path.join(profile_dir, "voice_profile.json")

    profile_data = {
        "mean_vector": mean_profile_vector.tolist(),
        "threshold": 0.73,
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "enrolled_phrases": [
            "Jarvis", "Hey Jarvis", "Jarvis bhai", "Jarvis ji", 
            "Sun Jarvis", "Chalo utho Jarvis", "Utho Jarvis", "Arre Jarvis"
        ]
    }

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2)
        print("\n" + "="*65)
        print(f"  🎉 SUCCESS: Voice profile saved to '{profile_path}'!")
        print("  JARVIS is now locked to YOUR voice print for all Hinglish wake words.")
        print("="*65 + "\n")
    except Exception as err:
        logger.error(f"Failed to write voice profile to disk: {err}")
        return False

    # Perform live verification test
    print("--- LIVE VERIFICATION TEST ---")
    print("Say any Hinglish wake word (e.g. 'Jarvis', 'Hey Jarvis', 'Sun Jarvis') to verify...")
    input("Press ENTER, then speak your wake word... ")
    
    test_audio = record_audio_sample(duration_sec=2.2, sample_rate=16000)
    test_vec = compute_mean_mfcc(test_audio, sample_rate=16000)
    sim = cosine_similarity(test_vec, mean_profile_vector)

    print(f"\n  Speaker Voice Match Similarity: {sim:.3f} (Threshold: 0.73)")
    if sim >= 0.73:
        print("  ✅ VERIFICATION SUCCESS: Your Hinglish voice was matched & verified!")
    else:
        print("  ⚠ Low similarity score. Don't worry, JARVIS dynamic voice print adaptation will refine it as you use it.")

    print("\nSetup complete! Run 'python main.py' to start JARVIS.\n")
    return True

if __name__ == "__main__":
    run_voice_enrollment()
