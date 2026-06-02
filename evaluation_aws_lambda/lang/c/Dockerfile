# C language image layered on the common base.
# The base image already installs build-essential (gcc/make).

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

# Sanity check the toolchain availability and C11 support
RUN gcc --version \
 && printf '#include <stdio.h>\nint main(void){puts("ok");return 0;}\n' > /tmp/t.c \
 && gcc -std=c11 -O2 /tmp/t.c -o /tmp/t \
 && /tmp/t | grep -q '^ok$' \
 && rm -f /tmp/t.c /tmp/t

# Base image already sets the Lambda entrypoint and copies /var/task.
