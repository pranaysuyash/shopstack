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
        "openai": [
            "openai>=1.0",
        ],
        "local": [
            "llama-cpp-python>=0.3",
        ],
    },
)
