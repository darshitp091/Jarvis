import sys
import os
import time
import numpy as np
import sounddevice as sd
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.wake_word import compute_mean_mfcc, cosine_similarity

def run_calibration():
    print("==========================================================")
    print("         JARVIS VOICE ID CALIBRATION UTILITY             ")
    print("==========================================================")
    print("This utility will record your voice saying 'Hey JARVIS' 5 times")
    print("to calibrate your voiceprint and enable Speaker Verification.")
    print("No heavy AI or CUDA models will be loaded during this run.\n")
    
    sentences = [
        "Hey JARVIS (Attempt 1)",
        "Hey JARVIS (Attempt 2)",
        "Hey JARVIS (Attempt 3)",
        "Hey JARVIS (Attempt 4)",
        "Hey JARVIS (Attempt 5)"
    ]
    
    sample_rate = 16000
    duration_sec = 2.5
    utterance_mfccs = []
    
    i = 0
    while i < len(sentences):
        print(f"\n[Sentence {i+1} of {len(sentences)}]")
        print("----------------------------------------------------------")
        print(f"\" {sentences[i]} \"")
        print("----------------------------------------------------------")
        input("Press Enter when you are ready to speak, then read the sentence aloud...")
        
        # Small delay to avoid capturing Enter key press noise
        time.sleep(0.3)
        print(">>> RECORDING... Speak now.")
        
        try:
            recording = sd.rec(int(duration_sec * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
            sd.wait()
            print(">>> RECORDING COMPLETE. Processing...")
            
            audio_data = np.squeeze(recording)
            
            # Check energy / voice presence
            audio_float = audio_data.astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_float**2))
            
            if rms < 0.002:
                print("\n[Warning] The recording was too quiet or no voice was detected.")
                print("Please ensure your microphone is connected and try reading the sentence again.")
                continue
                
            # Extract MFCC
            mean_mfcc = compute_mean_mfcc(audio_float, sample_rate)
            utterance_mfccs.append(mean_mfcc)
            i += 1
            
        except Exception as e:
            print(f"\n[Error] Failed to capture audio: {e}")
            print("Let's retry this sentence.")
            continue
            
    print("\n==========================================================")
    print("Analyzing voiceprint consistency...")
    
    # Calculate all pairwise similarities
    similarities = []
    for idx1 in range(len(utterance_mfccs)):
        for idx2 in range(idx1 + 1, len(utterance_mfccs)):
            sim = cosine_similarity(utterance_mfccs[idx1], utterance_mfccs[idx2])
            similarities.append(sim)
            
    min_sim = min(similarities)
    avg_sim = sum(similarities) / len(similarities)
    
    print(f" - Average Voice Consistency: {avg_sim:.4f}")
    print(f" - Minimum Pairwise Similarity: {min_sim:.4f}")
    
    # Calculate mean vector across all 5 utterances
    mean_vector = np.mean(utterance_mfccs, axis=0)
    
    # Adaptive threshold: min_sim - 0.05, bounded between 0.72 and 0.80
    adaptive_threshold = max(0.72, min(0.80, min_sim - 0.05))
    print(f" - Calibrated Similarity Threshold: {adaptive_threshold:.3f}")
    
    profile = {
        "mean_vector": mean_vector.tolist(),
        "threshold": adaptive_threshold
    }
    
    os.makedirs("config", exist_ok=True)
    profile_path = "config/voice_profile.json"
    try:
        with open(profile_path, "w") as f:
            json.dump(profile, f, indent=2)
        print("\n[Success] Voice print saved successfully to config/voice_profile.json!")
        print("Speaker Verification is now configured and active.")
        print("You can now start JARVIS by running main.py.")
    except Exception as e:
        print(f"\n[Error] Failed to save voice profile: {e}")
        
    print("==========================================================")

if __name__ == "__main__":
    run_calibration()
