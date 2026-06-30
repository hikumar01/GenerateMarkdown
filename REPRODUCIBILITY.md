# Reproducibility

The source of truth for installable dependencies is `pyproject.toml`.

This project intentionally does not commit a universal lock file because the optional audio and design stacks are platform-sensitive:

- Apple Silicon users normally install `mlx-whisper`.
- Intel users may choose `openai-whisper` instead.
- Some conversion quality comes from system tools installed through Homebrew, not Python packages.

For a reproducible local run, create a lock from a clean environment on the machine that will run the converter:

```bash
python3.13 -m venv ~/md-convert-env
source ~/md-convert-env/bin/activate
pip install --upgrade pip
pip install -e '.[apple-silicon-transcription,design]'
python -m pip freeze --local > requirements-lock.txt
```

To recreate that exact Python environment later:

```bash
python3.13 -m venv ~/md-convert-env
source ~/md-convert-env/bin/activate
pip install --upgrade pip
pip install -r requirements-lock.txt
pip install -e . --no-deps
```

Keep the generated `requirements-lock.txt` with your converted corpus or automation if exact repeatability matters. Do not assume a lock generated on Apple Silicon is the right lock for Intel, Linux, or a machine using a different transcription backend.

System tools are still outside the Python lock. Capture them separately when exact machine reproduction matters:

```bash
brew bundle dump --file Brewfile --force
```