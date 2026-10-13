# The local app image was built by this audit; its immutable digest is recorded
# in phase6-compatible-client-build.log and the final container receipt.
ARG CONCIERGE_VERSION=phase6-local
FROM concierge-ai:${CONCIERGE_VERSION:-local}
USER root
RUN python -m pip install --no-cache-dir pytest==9.1.1
USER concierge
WORKDIR /work
