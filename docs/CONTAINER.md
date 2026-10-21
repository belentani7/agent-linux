# Agent Linux container — reproducible core

The existing Agent Linux project now has a deliberately small unprivileged image.
It installs Ubuntu 26.04 packaged Bash, Git, GitHub CLI, Python, Node/npm, jq,
ripgrep and basic build tools without embedding any GitHub secrets or executing
remote vendor installer scripts during the Docker build.

To verify: run docker build --pull -t agent-linux:dev ., then run the image
with --network none, --read-only, --cap-drop ALL and --security-opt no-new-privileges.
The exact smoke invocation is in the container CI workflow. Run the source
contracts with python3 -m unittest discover -s tests -p test_container.py -v.

Rootless runtime UID: 10001. Image alone does not install or run Claude Code,
OpenClaw, PowerShell, Go, Rust or a Playwright browser. Optional AI agents need
interactive user authorization and a reviewed vendor installer or host setup.
The separate host install.sh remains unchanged. No CI green claim is made until
the hosted Docker build and runtime smoke job actually pass.
