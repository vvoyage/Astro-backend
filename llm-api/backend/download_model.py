from backend.logger import setup_logging, get_logger
from backend.llama_engine import warmup_llama_engine


def main() -> None:
    setup_logging()
    logger = get_logger("llm-api.model-downloader")
    logger.info("model_warmup_started")
    warmup_llama_engine()
    logger.info("model_warmup_completed")


if __name__ == "__main__":
    main()

