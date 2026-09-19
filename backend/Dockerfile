FROM python:3.11-slim

# ffmpeg is required by Whisper to decode audio files.
# build-essential is needed because some Python packages (numba, llvmlite,
# which whisper depends on) build native extensions from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installing dependencies first, separately from app code, so Docker
# can cache this layer and skip the slow reinstall whenever only the
# application code changes, not the dependencies.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install the CPU-only build of torch before the rest of the
# requirements. openai-whisper depends on torch without specifying
# CPU or GPU, so left to its own devices pip pulls the full CUDA
# build, which drags in several gigabytes of GPU libraries that are
# useless on ordinary CPU-only hosting. Installing this first means
# the later requirements install finds torch already satisfied and
# leaves it alone.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
