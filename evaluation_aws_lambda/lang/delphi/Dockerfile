# Delphi (Pascal) image layered on the common base using Free Pascal (FPC).

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Install Free Pascal compiler
RUN apt-get update -yqq \
 && apt-get install -yqq --no-install-recommends fpc \
 && rm -rf /var/lib/apt/lists/*

# Sanity check: compile and run a tiny Pascal program
RUN printf "program P; begin writeln('ok'); end.\n" > /tmp/p.pas \
 && fpc -O1 -v0 /tmp/p.pas -o/tmp/p >/dev/null 2>&1 \
 && /tmp/p | grep -q '^ok$' \
 && rm -f /tmp/p.pas /tmp/p \
 && fpc -iV

# Base image already sets the Lambda entrypoint and copies /var/task.

