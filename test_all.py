import os
import sys

try:
    import numpy as np
    print(f"Numpy version: {np.__version__}")
except Exception as e:
    print(f"Numpy import error: {e}")

try:
    import huggingface_hub
    print(f"huggingface_hub version: {huggingface_hub.__version__}")
except Exception as e:
    print(f"huggingface_hub import error: {e}")

try:
    import transformers
    print(f"transformers version: {transformers.__version__}")
except Exception as e:
    print(f"transformers import error: {e}")

try:
    from TTS.api import TTS
    print("TTS (coqui-tts) import success")
except Exception as e:
    print(f"TTS import error: {e}")

try:
    import whisperx
    print("WhisperX import success")
except Exception as e:
    print(f"WhisperX import error: {e}")

print("\n--- Testing WhisperX Diarization Pipeline initialization (with out token) ---")
try:
    # This just tests the __init__ call and patching
    pipeline = whisperx.DiarizationPipeline(use_auth_token=None, device="cpu")
    print("WhisperX DiarizationPipeline __init__ success (without token)")
except Exception as e:
    print(f"WhisperX DiarizationPipeline __init__ error: {e}")

print("\nAll checks complete.")
