from __future__ import annotations

import modal
from pydantic import BaseModel

app = modal.App("shopstack-embeddings")

image = (modal.Image.debian_slim(python_version="3.12")
    .pip_install("sentence-transformers>=3.4.0", "numpy>=2.0.0")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"}))


class EmbeddingsInferRequest(BaseModel):
    texts: list[str] = []
    text: str = ""
    model: str = "shopstack-embeddings"


class EmbeddingsInferResponse(BaseModel):
    embeddings: list[list[float]]
    embedding_dim: int = 0
    count: int = 0
    latency_s: float = 0.0
    model_id: str = ""


@app.cls(image=image, gpu="T4", timeout=120,     scaledown_window=60,
         volumes={"/models": modal.Volume.from_name("shopstack-model-cache", create_if_missing=True)})
class EmbeddingsModel:
    def __init__(self):
        self.model_id = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self.model = None

    @modal.enter()
    def load_model(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(
            self.model_id,
            cache_folder="/models/embeddings",
        )

    @modal.fastapi_endpoint(method="POST", label="embeddings-infer")
    def embed(self, body: EmbeddingsInferRequest) -> EmbeddingsInferResponse:
        import time

        texts = body.texts
        if not texts and body.text:
            texts = [body.text]
        if not texts:
            return EmbeddingsInferResponse(
                embeddings=[], model_id=self.model_id
            )
        start = time.perf_counter()
        embeddings = self.model.encode(texts, normalize_embeddings=True).tolist()
        elapsed = time.perf_counter() - start
        return EmbeddingsInferResponse(
            model_id=self.model_id,
            embedding_dim=len(embeddings[0]) if embeddings else 0,
            count=len(embeddings),
            latency_s=round(elapsed, 3),
            embeddings=embeddings,
        )


@app.local_entrypoint()
def main():
    print("Deploy: modal deploy shopstack.modal.embeddings.deploy")
