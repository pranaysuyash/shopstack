from __future__ import annotations

import os

import modal
from pydantic import BaseModel

from shopstack.modal.shared import (
    A10G,
    MODEL_CACHE_PATH,
    MODEL_CACHE_VOLUME,
    base_image,
)

app = modal.App("shopstack-planner")

image = base_image(extra_packages=["vllm>=0.8.0"])


class PlannerInferRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    model: str = "shopstack-planner"
    system: str = ""
    kwargs: dict = {}


class PlannerInferResponse(BaseModel):
    text: str
    model_id: str
    latency_s: float
    tool_calls: list = []
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@app.cls(
    image=image,
    gpu=A10G,
    timeout=300,
    scaledown_window=60,
    volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME},
    secrets=[modal.Secret.from_dict({"HF_TOKEN": os.environ.get("HF_TOKEN", "")})],
)
class PlannerModel:
    def __init__(self):
        self.model_id = "minicpm/Ministral-8B-Instruct-2410"
        self.model = None
        self.tokenizer = None

    @modal.enter()
    def load_model(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_path = os.path.join(MODEL_CACHE_PATH, "planner", self.model_id.replace("/", "_"))
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            cache_dir=model_path,
            trust_remote_code=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            cache_dir=model_path,
            device_map="auto",
            torch_dtype="auto",
            trust_remote_code=True,
        )

    def _build_prompt(self, body: PlannerInferRequest) -> str:
        if body.system:
            return f"{body.system}\n\n{body.prompt}"
        return body.prompt

    @modal.fastapi_endpoint(method="POST", label="planner-infer")
    def infer(self, body: PlannerInferRequest) -> PlannerInferResponse:
        import time

        prompt = self._build_prompt(body)
        messages = [{"role": "user", "content": prompt}]
        inputs = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to("cuda")

        start = time.perf_counter()
        outputs = self.model.generate(
            inputs,
            max_new_tokens=body.max_tokens,
            temperature=0.1,
            do_sample=True,
        )
        elapsed = time.perf_counter() - start
        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        prompt_len = inputs.shape[1]
        completion_len = outputs.shape[1] - prompt_len

        return PlannerInferResponse(
            text=text,
            model_id=self.model_id,
            latency_s=round(elapsed, 3),
            usage={
                "prompt_tokens": prompt_len,
                "completion_tokens": completion_len,
                "total_tokens": prompt_len + completion_len,
            },
        )


@app.local_entrypoint()
def main():
    print("Deploy: modal deploy shopstack.modal.planner.deploy")
