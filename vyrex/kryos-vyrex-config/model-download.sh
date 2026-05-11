#!/bin/bash
# Downloads default models on first boot
set -e

MODELS_DIR=/var/vyrex/models
sudo mkdir -p $MODELS_DIR
sudo chown -R $USER:$USER $MODELS_DIR

echo "Downloading Qwen2.5-7B (primary reasoning model)..."
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m.gguf \
  --local-dir $MODELS_DIR

echo "Downloading LLaVA (vision model)..."
huggingface-cli download mys/ggml_llava-v1.5-7b \
  mmproj-model-f16.gguf ggml-model-q4_k.gguf \
  --local-dir $MODELS_DIR/llava

echo "Downloading Whisper Base (speech-to-text)..."
wget -O $MODELS_DIR/whisper-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

echo "Model download complete."
