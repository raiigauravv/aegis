# kb_query: ONNX MiniLM (fastembed) + FAISS retrieval (arm64 Lambda container).
# fastembed over sentence-transformers/torch: ~40MB runtime vs ~2GB, which keeps
# cold start in single-digit seconds (torch import alone blew the 60s budget).
FROM public.ecr.aws/lambda/python:3.12-arm64

RUN pip install --no-cache-dir fastembed faiss-cpu numpy boto3 pydantic

# Bake the model: no network / HF pulls at runtime.
RUN python -c "from fastembed import TextEmbedding; \
    TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/opt/model')"

COPY shared/aegis_core ${LAMBDA_TASK_ROOT}/aegis_core
COPY services/kb_query/handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
