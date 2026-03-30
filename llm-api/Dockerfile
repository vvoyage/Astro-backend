FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

ARG DEFAULT_LLAMA_MODEL=llama-3.1-8b-instruct
ENV LLAMA_MODEL=${DEFAULT_LLAMA_MODEL}
ENV GPU_ENABLED=true
ENV CONTEXT_SIZE=2048
ENV MAX_TOKENS=512
ENV HF_HOME=/app/.cache/huggingface
ENV LLAMA_CPP_VERBOSE=0
# HuggingFace download settings (5 min timeout per chunk, use mirror if available)
ENV HF_HUB_DOWNLOAD_TIMEOUT=300
ENV HF_HUB_ENABLE_HF_TRANSFER=0

WORKDIR /app

ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone


# Install Python 3.11 and system dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    python3-pip \
    build-essential \
    cmake \
    git \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Set up CUDA library paths for linking
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/lib:${LD_LIBRARY_PATH}
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=/usr/local/cuda/bin:${PATH}

# Set python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Upgrade pip
RUN python3 -m pip install --upgrade pip

# Create cache directory for HuggingFace models
RUN mkdir -p /app/.cache/huggingface

# Copy dependency specification
COPY requirements.txt .

# Install Python dependencies with CUDA support for llama-cpp-python
# Use GGML_CUDA instead of deprecated LLAMA_CUBLAS
# Set CUDA paths explicitly for CMake
# Disable examples and use CMake flags to allow undefined symbols for libcuda.so.1
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_BUILD_TYPE=Release -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined -DCMAKE_SHARED_LINKER_FLAGS=-Wl,--allow-shlib-undefined"
ENV FORCE_CMAKE=1
# Verify CUDA libraries are accessible and update library cache
RUN ldconfig
# Install all dependencies (llama-cpp-python will be built with CUDA support)
# libcuda.so.1 (driver library) will be available at runtime from host via --gpus flag
RUN pip install --no-cache-dir -r requirements.txt

# Copy application sources
COPY backend/ ./backend/

# Note: Model download is skipped during build (requires libcuda.so.1 which is only available at runtime)
# Model will be automatically downloaded on first application startup when container runs with --gpus flag
# To pre-download model, run: docker run --gpus all <image> python -m backend.download_model

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI via Uvicorn
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

