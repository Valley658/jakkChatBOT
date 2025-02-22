import subprocess
import sys
import openai

try:
    from transformers import pipeline
except ImportError as e:
    if 'Keras 3' in str(e):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tf-keras"])
        import tensorflow as tf
        sys.modules['keras'] = tf.keras
        from transformers import pipeline
    else:
        raise e

# Ensure PyTorch is installed and available
import torch
assert torch.__version__ >= "1.0.0", "PyTorch version must be at least 1.0.0"

chatbot_pipeline = pipeline('text-generation', model='microsoft/DialoGPT-medium')

def get_response(user_input, model="text-davinci-003"):
    response = openai.Completion.create(
        engine=model,
        prompt=user_input,
        max_tokens=150
    )
    return response.choices[0].text.strip()

def get_available_models():
    return ["text-davinci-003", "text-curie-001", "text-babbage-001", "text-ada-001"]