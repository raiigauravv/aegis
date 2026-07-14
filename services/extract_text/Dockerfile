# extract_text: Tesseract + pdfplumber + poppler (arm64 Lambda container)
FROM public.ecr.aws/docker/library/python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir awslambdaric pdfplumber pytesseract pdf2image pillow boto3 pydantic

WORKDIR /var/task
COPY shared/aegis_core /var/task/aegis_core
COPY services/extract_text/handler.py /var/task/

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
