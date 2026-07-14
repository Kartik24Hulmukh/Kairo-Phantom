# Vendored Embedding Model: all-MiniLM-L6-v2

## Model
- **Name:** all-MiniLM-L6-v2 (quantized ONNX variant)
- **Source:** [Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2) on HuggingFace
- **Original model:** [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- **File:** `model.onnx` (quantized, ~22MB) — originally `onnx/model_quantized.onnx`
- **Embedding dimension:** 384 (truncated to 256 in application code)
- **Pooling:** Mean

## License
- **Model license:** Apache-2.0
- The model weights and tokenizer files are distributed under the Apache License 2.0,
  as stated on the HuggingFace model page.
- This project (Kairo-Phantom) is MIT-licensed; the vendored model files retain
  their original Apache-2.0 license.

## Files
| File | Description |
|------|-------------|
| `model.onnx` | Quantized ONNX model (dynamic quantization) |
| `tokenizer.json` | HuggingFace fast tokenizer |
| `config.json` | Model configuration (BERT, hidden_size=384) |
| `special_tokens_map.json` | Special tokens (CLS, SEP, PAD, UNK, MASK) |
| `tokenizer_config.json` | Tokenizer configuration (BertTokenizer) |

## Offline Usage
These files are embedded into the binary at compile time via `include_bytes!`/`include_str!`
in `phantom-core/src/embedding.rs`. No network access is required at runtime. This is critical
for Kairo-Phantom's offline-first, air-gapped product promise.
