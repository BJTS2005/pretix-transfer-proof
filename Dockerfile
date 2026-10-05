FROM pretix/standalone:stable
USER root
COPY . /pretix-transfer-proof
RUN pip3 install /pretix-transfer-proof
USER pretixuser
RUN cd /pretix/src && make production
