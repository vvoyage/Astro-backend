#!/usr/bin/env python3
"""
Manual model downloader for llm-api service.
Use this script if HuggingFace CDN is slow or unavailable.

Usage:
    python download_model_manual.py [model_name]
    
Example:
    python download_model_manual.py llama-3.2-3b-instruct
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.logger import setup_logging, get_logger
from backend.llama_engine import MODEL_ALIASES, DEFAULT_MODEL_NAME, _resolve_model_name

logger = get_logger("llm-api.manual-downloader")


def download_model(model_name: str = DEFAULT_MODEL_NAME) -> None:
    """Download model using huggingface-cli for better reliability."""
    setup_logging()
    
    resolved_name = _resolve_model_name(model_name)
    logger.info("manual_download_started", model=model_name, resolved=resolved_name)
    
    # Create cache directory
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"Downloading model: {resolved_name}")
    print(f"Cache directory: {cache_dir}")
    print(f"{'='*70}\n")
    
    # Use huggingface-cli for more reliable downloads
    print("Using huggingface-cli for download...")
    print("If this fails, you can also download manually from:")
    print(f"  https://huggingface.co/{resolved_name}/tree/main")
    print("\nLooking for files matching: *Q4_K_M.gguf\n")
    
    try:
        import subprocess
        cmd = [
            "huggingface-cli",
            "download",
            resolved_name,
            "--include", "*Q4_K_M.gguf",
            "--cache-dir", str(cache_dir),
        ]
        
        logger.info("running_huggingface_cli", command=" ".join(cmd))
        result = subprocess.run(cmd, check=True, capture_output=False)
        
        if result.returncode == 0:
            logger.info("manual_download_completed", model=resolved_name)
            print(f"\n{'='*70}")
            print("✅ Model downloaded successfully!")
            print(f"{'='*70}\n")
            return
            
    except FileNotFoundError:
        print("\n⚠️  huggingface-cli not found. Installing...")
        print("Run: pip install huggingface_hub[cli]\n")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logger.error("manual_download_failed", error=str(e))
        print(f"\n❌ Download failed: {e}")
        print("\nAlternative: Download manually from HuggingFace website")
        print(f"1. Go to: https://huggingface.co/{resolved_name}/tree/main")
        print(f"2. Download file matching: *Q4_K_M.gguf")
        print(f"3. Place it in: {cache_dir}")
        print(f"4. Set LOCAL_MODEL_PATH=/path/to/downloaded/file.gguf\n")
        sys.exit(1)


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_NAME
    download_model(model)

