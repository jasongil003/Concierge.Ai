FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
WORKDIR /mock-ai
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.35.0
COPY mock_ai.py ./mock_ai.py
USER 65532:65532
EXPOSE 8081
CMD ["python", "mock_ai.py"]
