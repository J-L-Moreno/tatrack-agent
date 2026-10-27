FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

# Set by Terraform (--build-arg) to the deployment region.
ARG AWS_REGION=us-east-1

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=${AWS_REGION} \
    AWS_DEFAULT_REGION=${AWS_REGION}

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

# AgentCore Runtime contract: HTTP on 8080 (/invocations, /ping)
EXPOSE 8080

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "main"]
