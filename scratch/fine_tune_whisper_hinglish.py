"""
Whisper-Small Fine-Tuning Script for Hinglish (Hindi-English Code-Switched) ASR

This script contains the full logical code to load a Hinglish dataset from Hugging Face,
preprocess it, load the pre-trained openai/whisper-small model, and run the training loop
using the Hugging Face Trainer.

To run this script:
1. Activate virtual env: .\\jarvis_env\\Scripts\\activate
2. Install training dependencies: pip install transformers datasets soundfile librosa evaluate jinja2 accelerate
3. Execute the script: python scratch/fine_tune_whisper_hinglish.py
"""

import os
import torch
from dataclasses import dataclass
from typing import Any, Dict, List, Union
from datasets import load_dataset, Audio
from transformers import (
    WhisperProcessor,
    WhisperForConditionalGeneration,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
import evaluate

# ----------------------------------------------------
# 1. Configuration & Constants
# ----------------------------------------------------
MODEL_NAME = "openai/whisper-small"
LANGUAGE = "Hindi"
TASK = "transcribe"
DATASET_NAME = "agarwalayushi/hinglish"  # Hinglish Concatenated Audio Dataset
OUTPUT_DIR = os.path.abspath("./whisper-small-hinglish-finetuned")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Check GPU availability
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")
if device == "cuda":
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")

# ----------------------------------------------------
# 2. Load Dataset & Processor
# ----------------------------------------------------
print("Loading processor and dataset...")
processor = WhisperProcessor.from_pretrained(MODEL_NAME, language=LANGUAGE, task=TASK)

# Load training and validation splits
# (Note: For this local fine-tuning run, we load a subset of the first 500 samples
# to fit within local compute bounds, rather than the full 2,200 hours).
try:
    dataset = load_dataset(DATASET_NAME, split={"train": "train[:500]", "validation": "validation[:50]"})
    print("Dataset splits loaded successfully!")
    print(dataset)
except Exception as e:
    print(f"Could not load '{DATASET_NAME}' directly: {e}")
    print("Falling back to loading google/fleurs (Hindi subset)...")
    dataset = load_dataset("google/fleurs", "hi_in", split={"train": "train[:500]", "validation": "validation[:50]"})

# Whisper expects audio sampled at 16kHz mono. Let's cast the audio column to match this.
dataset = dataset.cast_column("audio", Audio(sampling_rate=16000))

# ----------------------------------------------------
# 3. Preprocessing Functions
# ----------------------------------------------------
def prepare_dataset(batch):
    # Extract audio features (Log-Mel Spectrogram)
    audio = batch["audio"]
    batch["input_features"] = processor.feature_extractor(
        audio["array"], sampling_rate=audio["sampling_rate"]
    ).input_features[0]

    # Encode target transcripts to label ids
    # Note: If the dataset has a different transcription column (e.g. 'sentence' or 'text'), update it here
    transcript_column = "transcription" if "transcription" in batch else "sentence"
    batch["labels"] = processor.tokenizer(batch[transcript_column]).input_ids
    return batch

print("Preprocessing dataset (extracting Mel spectrograms and tokenizing)...")
# Map dataset to preprocessing function (select first 1000 items for faster demo runs if desired)
processed_dataset = dataset.map(
    prepare_dataset, 
    remove_columns=list(dataset.column_names.values())[0],  # remove all old columns
    num_proc=1
)

# ----------------------------------------------------
# 4. Data Collator for Seq2Seq
# ----------------------------------------------------
@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: Any

    def __call__(self, features: List[Dict[str, Union[List[int], torch.Tensor]]]) -> Dict[str, torch.Tensor]:
        # Split input features and label sequences
        input_features = [{"input_features": feature["input_features"]} for feature in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        label_features = [{"input_ids": feature["labels"]} for feature in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")

        # Replace padding token id with -100 so PyTorch CrossEntropyLoss ignores it
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        # Remove decoder start token if present during padding
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch

data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)

# ----------------------------------------------------
# 5. Metrics Definition (Word Error Rate)
# ----------------------------------------------------
wer_metric = evaluate.load("wer")

def compute_metrics(pred):
    pred_ids = pred.predictions
    label_ids = pred.label_ids

    # Replace -100 back to pad_token_id for proper decoding
    label_ids[label_ids == -100] = processor.tokenizer.pad_token_id

    pred_str = processor.tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
    label_str = processor.tokenizer.batch_decode(label_ids, skip_special_tokens=True)

    wer = 100 * wer_metric.compute(predictions=pred_str, references=label_str)
    return {"wer": wer}

# ----------------------------------------------------
# 6. Model Initialization
# ----------------------------------------------------
print("Initializing model...")
model = WhisperForConditionalGeneration.from_pretrained(MODEL_NAME)

# Set model configurations for generation
model.config.forced_decoder_ids = None
model.config.suppress_tokens = []
# Ensure model checkpoints are compatible with frozen features
model.config.use_cache = False

# ----------------------------------------------------
# 7. Training Arguments
# ----------------------------------------------------
training_args = Seq2SeqTrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=1,  # Reduced batch size to 1 to prevent CUDA OOM
    gradient_accumulation_steps=16, # Kept effective batch size at 16
    learning_rate=1e-5,
    warmup_steps=50,
    max_steps=100,          # Running a short 100-step training session for verification
    gradient_checkpointing=True,
    fp16=torch.cuda.is_available(),
    optim="adafactor",      # Use memory-efficient Adafactor optimizer to save ~1.5GB VRAM
    evaluation_strategy="steps",
    per_device_eval_batch_size=1,
    predict_with_generate=True,
    generation_max_length=225,
    save_steps=50,
    eval_steps=50,
    logging_steps=5,
    report_to=["tensorboard"],
    load_best_model_at_end=True,
    metric_for_best_model="wer",
    greater_is_better=False,
    push_to_hub=False,
)

# ----------------------------------------------------
# 8. Initialize Trainer & Start Training
# ----------------------------------------------------
def get_trainer(args_obj, model_obj):
    return Seq2SeqTrainer(
        args=args_obj,
        model=model_obj,
        train_dataset=processed_dataset["train"],
        eval_dataset=processed_dataset["validation"] if "validation" in processed_dataset else processed_dataset["test"],
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        tokenizer=processor.feature_extractor,
    )

trainer = get_trainer(training_args, model)

print("Starting training loop (running 100 steps on GPU/CPU)...")
try:
    trainer.train()
except Exception as e:
    import traceback
    err_str = str(e) + "\n" + traceback.format_exc()
    if "OutOfMemory" in err_str or "out of memory" in err_str or "CUDA error" in err_str:
        print("\n[WARNING] CUDA Out of Memory detected. Falling back to CPU training...")
        
        # Reset memory cache
        torch.cuda.empty_cache()
        
        # Update training arguments for CPU
        training_args.no_cuda = True
        training_args.fp16 = False
        training_args.max_steps = 10  # Reduced steps on CPU to keep it fast
        training_args.eval_steps = 5
        training_args.save_steps = 5
        training_args.logging_steps = 1
        
        # Re-initialize model and trainer on CPU
        model.to("cpu")
        trainer = get_trainer(training_args, model)
        
        print("Retrying training loop on CPU (running 10 steps)...")
        trainer.train()
    else:
        raise e

print(f"Saving final fine-tuned model weights to: {OUTPUT_DIR}")
try:
    model.save_pretrained(OUTPUT_DIR)
    processor.save_pretrained(OUTPUT_DIR)
except Exception as save_err:
    print(f"Error saving pretrained weights: {save_err}")

print("\n--- Fine-tuning Complete! ---")
print(f"Checkpoints and final model weights saved under: {OUTPUT_DIR}")
