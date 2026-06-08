# Lean language image layered on the common base.

ARG BASE_IMAGE=multipl-e-evaluation-base:latest
FROM ${BASE_IMAGE}

ENV ELAN_HOME=/opt/elan

# Install elan (Lean toolchain manager) and set stable toolchain under /opt
RUN curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -o /tmp/elan-init.sh \
 && env HOME=/opt bash /tmp/elan-init.sh -y --default-toolchain stable \
 && rm -f /tmp/elan-init.sh

ENV PATH="${ELAN_HOME}/bin:${PATH}"

# Ensure the installed toolchain is runnable by the Lambda user. Link the real
# toolchain binaries instead of elan shims, because elan writes update-check
# state under ELAN_HOME and Lambda's image filesystem is read-only at runtime.
RUN chmod -R a+rx ${ELAN_HOME} \
 && ${ELAN_HOME}/bin/lean --version \
 && ${ELAN_HOME}/bin/lake --version \
 && ln -sf "$(${ELAN_HOME}/bin/elan which lean)" /usr/local/bin/lean \
 && ln -sf "$(${ELAN_HOME}/bin/elan which lake)" /usr/local/bin/lake

# Sanity check
RUN /usr/local/bin/lean --version \
 && /usr/local/bin/lake --version \
 && elan --version

# Base image already sets the Lambda entrypoint and copies /var/task.
