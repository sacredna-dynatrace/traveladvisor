FROM python:3.11-bookworm

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Pre-download the local embedding model used when LLM_PROVIDER=anthropic (no embeddings API at Anthropic)
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

COPY app.py  ./
COPY ./public ./public
COPY ./destinations ./destinations
COPY ./models ./models
COPY ./pipeline ./pipeline
COPY ./tools ./tools
COPY ./utils ./utils

EXPOSE 8080

CMD [ "python", "app.py"]