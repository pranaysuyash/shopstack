from setuptools import find_packages, setup

setup(
    name="shopstack",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "gradio>=5",
        "pydantic>=2",
        "pydantic-settings>=2",
        "huggingface_hub>=0.20",
        "httpx>=0.25",
        "pydub",
        "pillow",
        "pandas",
    ],
    extras_require={
        "dev": [
            "pytest>=9",
            "pytest-cov",
            "pytest-benchmark",
        ],
        "cloud": [
            "openai>=1.0",
        ],
        "local": [
            "llama-cpp-python>=0.3",
        ],
        "otel": [
            "opentelemetry-api>=1.30",
            "opentelemetry-sdk>=1.30",
            "opentelemetry-exporter-otlp-proto-grpc>=1.30",
        ],
        "eval": [
            "ruff>=0.9",
        ],
    },
)
