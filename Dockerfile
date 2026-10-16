FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl wget gnupg git git-lfs gh openssh-client \
  build-essential python3 python3-pip python-is-python3 \
  jq yq ripgrep fd-find fzf shellcheck tmux zsh chromium-browser \
  && rm -rf /var/lib/apt/lists/*
RUN wget -q https://packages.microsoft.com/config/ubuntu/26.04/packages-microsoft-prod.deb -O /tmp/ms.deb \
  && dpkg -i /tmp/ms.deb && rm /tmp/ms.deb \
  && apt-get update && apt-get install -y --no-install-recommends powershell \
  && rm -rf /var/lib/apt/lists/*
RUN curl https://mise.run | sh
ENV PATH=/root/.local/bin:/root/.local/share/mise/installs/node/lts/bin:$PATH
RUN mise settings set experimental true && mise use --global node@lts && corepack enable \
  && npm install -g playwright typescript tsx prettier eslint
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard
WORKDIR /workspace
CMD ["bash"]
