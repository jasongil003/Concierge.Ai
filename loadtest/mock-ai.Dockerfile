FROM python:3.12-slim
WORKDIR /mock-ai
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.35.0
COPY mock_ai.py ./mock_ai.py
USER 65532:65532
EXPOSE 8081
CMD ["python", "mock_ai.py"]
