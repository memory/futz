FROM gliderlabs/alpine

RUN apk add --update \
    python \
    python-dev \
    py-pip \
  && pip install -U pip \
  && pip install -U virtualenv \
  && rm -rf /var/cache/apk/*

RUN virtualenv /futz
ADD requirements.txt /futz
ADD talamasca.py /futz/bin/talamasca.py
RUN /futz/bin/pip install -r /futz/requirements.txt
EXPOSE 80
CMD ["/futz/bin/python", "/futz/bin/talamasca.py"]
