# enrich_nlp: Presidio + spaCy + langdetect + VADER (arm64 Lambda container)
FROM public.ecr.aws/lambda/python:3.12-arm64

RUN pip install --no-cache-dir presidio-analyzer langdetect vaderSentiment boto3 pydantic \
    && python -m spacy download en_core_web_sm

COPY shared/aegis_core ${LAMBDA_TASK_ROOT}/aegis_core
COPY services/enrich_nlp/redactor.py services/enrich_nlp/handler.py \
     services/enrich_nlp/moderation.py ${LAMBDA_TASK_ROOT}/

# Default CMD is enrichment; the moderation_gate Lambda reuses this image with
# an image_config command override -> moderation.lambda_handler
CMD ["handler.lambda_handler"]
