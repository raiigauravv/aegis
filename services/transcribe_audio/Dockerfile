# transcribe_audio: faster-whisper small int8 (arm64 Lambda container)
FROM public.ecr.aws/lambda/python:3.12-arm64

RUN pip install --no-cache-dir faster-whisper boto3 pydantic

# Bake the model: convert/download at build so runtime needs no network.
RUN python -c "from faster_whisper import download_model; \
    download_model('small', output_dir='/opt/whisper-small')"

COPY shared/aegis_core ${LAMBDA_TASK_ROOT}/aegis_core
COPY services/transcribe_audio/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
