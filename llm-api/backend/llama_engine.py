import os
import threading
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from llama_cpp import Llama
from huggingface_hub import hf_hub_download, HfFileSystem

from backend.logger import get_logger

logger = get_logger("llm-api.llama_engine")

MODEL_ENV_VAR = "LLAMA_MODEL"
DEFAULT_MODEL_NAME = "llama-3.2-3b-instruct"
GPU_ENV_VAR = "GPU_ENABLED"
CONTEXT_SIZE_ENV_VAR = "CONTEXT_SIZE"
MAX_TOKENS_ENV_VAR = "MAX_TOKENS"
LOCAL_MODEL_PATH_ENV_VAR = "LOCAL_MODEL_PATH"

DEFAULT_CONTEXT_SIZE = 2048
DEFAULT_MAX_TOKENS = 512

_TRUE_VALUES = {"1", "true", "yes", "on"}

# Mapping model names to HuggingFace model IDs in GGUF format
MODEL_ALIASES = {
    "llama-3.2-3b-instruct": "bartowski/Llama-3.2-3B-Instruct-GGUF",
    "llama-3.1-8b-instruct": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
    "llama-3-8b-instruct": "bartowski/Meta-Llama-3-8B-Instruct-GGUF",
    "llama-2-7b-chat": "TheBloke/Llama-2-7B-Chat-GGUF",
}


class GenerationError(Exception):
    """Raised when the Llama generation flow fails."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"invalid_env_var_using_default", var_name=name, default=default)
        return default


def _resolve_model_name(raw_value: Optional[str]) -> str:
    if not raw_value:
        return DEFAULT_MODEL_NAME
    value = raw_value.strip().lower()
    return MODEL_ALIASES.get(value, raw_value.strip())


class LlamaEngine:
    """Wrapper around llama-cpp-python with env-based configuration."""

    def __init__(self) -> None:
        raw_model_name = os.getenv(MODEL_ENV_VAR, DEFAULT_MODEL_NAME)
        self.model_name = _resolve_model_name(raw_model_name)
        gpu_requested = _env_bool(GPU_ENV_VAR, False)
        self.context_size = _env_int(CONTEXT_SIZE_ENV_VAR, DEFAULT_CONTEXT_SIZE)
        self.max_tokens = _env_int(MAX_TOKENS_ENV_VAR, DEFAULT_MAX_TOKENS)

        # Determine GPU layers (-1 = all layers on GPU, 0 = CPU only)
        self.n_gpu_layers = -1 if gpu_requested else 0

        if gpu_requested:
            logger.info(
                "loading_llama_model_gpu",
                model=self.model_name,
                n_gpu_layers=self.n_gpu_layers,
                context_size=self.context_size,
            )
        else:
            logger.info(
                "loading_llama_model_cpu",
                model=self.model_name,
                context_size=self.context_size,
            )

        # Check if local model path is provided
        local_model_path = os.getenv(LOCAL_MODEL_PATH_ENV_VAR)

        if local_model_path and Path(local_model_path).exists():
            # Load from local path
            logger.info("loading_model_from_local_path", path=local_model_path)
            try:
                self.model = Llama(
                    model_path=local_model_path,
                    n_ctx=self.context_size,
                    n_gpu_layers=self.n_gpu_layers,
                    verbose=False,
                )
            except Exception as exc:
                logger.error("local_model_load_failed", error=str(exc), exc_info=True)
                raise GenerationError(f"Failed to load local Llama model: {exc}") from exc
        else:
            # Load from HuggingFace with retry logic and resume support
            if local_model_path:
                logger.warning("local_model_path_not_found", path=local_model_path)

            logger.info("loading_model_from_huggingface", repo_id=self.model_name)

            max_retries = 3
            retry_delay = 30

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info("attempting_model_download", attempt=attempt, max_retries=max_retries)

                    # First, find the exact filename
                    fs = HfFileSystem()
                    files = fs.ls(self.model_name, detail=False)
                    gguf_file = next((f for f in files if f.endswith("Q4_K_M.gguf")), None)

                    if not gguf_file:
                        raise GenerationError(f"No Q4_K_M.gguf file found in {self.model_name}")

                    filename = gguf_file.split("/")[-1]
                    logger.info("found_model_file", filename=filename)

                    # Download with automatic resume support
                    model_path = hf_hub_download(
                        repo_id=self.model_name,
                        filename=filename,
                        resume_download=True,  # Automatically resume interrupted downloads
                        local_files_only=False,
                    )

                    logger.info("model_downloaded", path=model_path)

                    # Load the downloaded model
                    self.model = Llama(
                        model_path=model_path,
                        n_ctx=self.context_size,
                        n_gpu_layers=self.n_gpu_layers,
                        verbose=False,
                    )
                    break  # Success, exit retry loop
                except Exception as exc:
                    error_msg = str(exc)
                    logger.warning(
                        "llama_model_load_attempt_failed",
                        attempt=attempt,
                        max_retries=max_retries,
                        error=error_msg[:200],
                    )
                    if attempt < max_retries:
                        logger.info("retrying_model_load", delay_seconds=retry_delay)
                        time.sleep(retry_delay)
                    else:
                        logger.error("llama_model_load_failed_all_attempts", error=error_msg[:500], exc_info=True)
                        raise GenerationError(
                            f"Failed to load Llama model after {max_retries} attempts: {error_msg[:200]}"
                        ) from exc

        logger.info(
            "llama_model_ready",
            model=self.model_name,
            gpu_layers=self.n_gpu_layers,
            context_size=self.context_size,
        )

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None,
        echo: bool = False,
    ) -> Dict[str, Any]:
        """
        Generic text generation with configurable parameters.
        Returns a dict with text, finish_reason, usage, raw_response.
        """
        if not prompt or not prompt.strip():
            raise GenerationError("Prompt is empty.")

        effective_max_tokens = max_tokens if max_tokens and max_tokens > 0 else self.max_tokens
        params = {
            "max_tokens": effective_max_tokens,
            "temperature": temperature if temperature is not None else 0.7,
            "top_p": top_p if top_p is not None else 0.95,
            "stop": stop,
            "echo": echo,
        }

        try:
            response = self.model(prompt, **params)
        except Exception as exc:
            logger.error("llama_generate_failed", error=str(exc), exc_info=True)
            raise GenerationError(f"Llama generate failed: {exc}") from exc

        if not response or "choices" not in response or not response["choices"]:
            raise GenerationError("Empty response from Llama model.")

        choice = response["choices"][0]
        generated_text = choice.get("text", "")
        if not echo:
            generated_text = generated_text.strip()

        if not generated_text:
            raise GenerationError("Generated text is empty.")

        return {
            "text": generated_text,
            "finish_reason": choice.get("finish_reason"),
            "usage": response.get("usage"),
            "raw_response": response,
        }


_llama_engine_instance: Optional[LlamaEngine] = None
_llama_engine_lock = threading.Lock()


def get_llama_engine() -> LlamaEngine:
    global _llama_engine_instance
    if _llama_engine_instance is None:
        with _llama_engine_lock:
            if _llama_engine_instance is None:
                _llama_engine_instance = LlamaEngine()
    return _llama_engine_instance


def warmup_llama_engine() -> None:
    """Ensure the Llama model is downloaded and cached."""
    get_llama_engine()

