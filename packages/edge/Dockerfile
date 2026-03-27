FROM nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.1-py3

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY configs ./configs
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app
CMD ["python", "-m", "src.main"]
