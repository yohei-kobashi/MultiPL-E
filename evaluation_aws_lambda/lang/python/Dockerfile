# Python language image layered on the common base.
# The base already installs Python 3 and required handler libraries.

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

# Install Python 2 alongside the base Python 3 and make it available as `python`.
RUN apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends python2 \
 && update-alternatives --install /usr/bin/python python /usr/bin/python2 1 \
 && rm -rf /var/lib/apt/lists/*

# Sanity check
RUN python3 -V \
 && python -V \
 && python3 - <<'PY' | grep -q '^ok$'
print('ok')
PY

# Base image already sets the Lambda entrypoint and copies /var/task.
