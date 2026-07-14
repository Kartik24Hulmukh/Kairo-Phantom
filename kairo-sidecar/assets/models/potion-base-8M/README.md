# Vendored Embedding Model: potion-base-8M

## Model
- **Name:** potion-base-8M (Model2Vec static embeddings)
- **HuggingFace id:** [minishlab/potion-base-8M](https://huggingface.co/minishlab/potion-base-8M)
- **Revision (vendored):** `bf8b056651a2c21b8d2565580b8569da283cab23`
- **Embedding dimension:** 256
- **Library:** [model2vec](https://github.com/MinishLab/model2vec) (`StaticModel.from_pretrained`)

## License
- **Model license:** MIT (as stated on the HuggingFace model card)
- This project (Kairo-Phantom) is MIT-licensed; the vendored model files retain
  their original MIT license from MinishLab.

## Files
| File | Description | Approx size |
|------|-------------|-------------|
| `model.safetensors` | Static embedding weights | ~29 MB |
| `tokenizer.json` | HuggingFace fast tokenizer | ~668 KB |
| `vocab.txt` | Vocabulary | ~216 KB |
| `config.json` | Model configuration | small |
| `modules.json` | Sentence-transformers modules metadata | small |
| `tokenizer_config.json` | Tokenizer configuration | small |
| `special_tokens_map.json` | Special tokens map | small |

## Offline usage
These files are committed directly to git (no Git LFS; under GitHub's 50 MB
limit). Python loaders resolve this directory via
`sidecar.model_paths.resolve_potion_base_8m_path()` and load with
`StaticModel.from_pretrained(<local path>, force_download=False)` while
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` are set. No network access is
required at runtime or in CI. This mirrors the Rust offline vendor path in
`phantom-core/assets/models/all-MiniLM-L6-v2/`.

Override path with env var `KAIRO_MODEL2VEC_PATH` if the tree is relocated.
