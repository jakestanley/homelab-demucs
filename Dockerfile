FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install torch with CUDA before requirements so pip doesn't pull the CPU build
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip3 install --no-cache-dir demucs

COPY demucs_service/ ./demucs_service/

CMD ["python3", "-m", "demucs_service.server"]
