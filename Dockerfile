FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends \
  bash ca-certificates curl git git-lfs gh openssh-client \
  build-essential python3 python3-venv python3-pip nodejs npm \
  jq ripgrep fd-find fzf shellcheck tar gzip unzip tini procps \
  && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 agent \
  && useradd --uid 10001 --gid 10001 --home-dir /home/agent --create-home --shell /bin/bash agent \
  && mkdir -p /workspace && chown agent:agent /workspace
WORKDIR /workspace
USER agent:agent
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash"]
