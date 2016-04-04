FROM python:2.7
MAINTAINER Katharine Berry <katharine@pebble.com>

RUN apt-get update && apt-get install -y \
  libglib2.0-dev libpixman-1-dev libfdt-dev gnutls-dev

ENV QEMU_VERSION 2.1.1-pebble1

RUN mkdir /qemu && cd /qemu && \
  curl -L https://github.com/pebble/qemu/archive/v${QEMU_VERSION}.tar.gz | tar xz --strip 1 && \
  ./configure --disable-werror --enable-debug --target-list="arm-softmmu" \
    --extra-cflags="-DSTM32_UART_NO_BAUD_DELAY -std=gnu99" --enable-vnc-ws --disable-sdl && \
  make -j4

ENV PYPKJS_VERSION 1.0

RUN git clone https://github.com/pebble/pypkjs.git --depth 1 --branch v$PYPKJS_VERSION --recursive

RUN virtualenv /pypkjs/.env && . /pypkjs/.env/bin/activate && pip install -r /pypkjs/requirements.txt

ENV FIRMWARE_VERSION 3.11

RUN mkdir /qemu-tintin-images && cd /qemu-tintin-images && \
  curl -L https://github.com/pebble/qemu-tintin-images/archive/v${FIRMWARE_VERSION}.tar.gz | tar xz --strip 1


ADD requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /code
WORKDIR /code

ENV QEMU_DIR=/qemu QEMU_BIN=/qemu/arm-softmmu/qemu-system-arm PKJS_BIN=/pypkjs/phonesim.py \
  PKJS_VIRTUALENV=/pypkjs/.env QCON_PORT=80 QEMU_IMAGE_ROOT=/qemu-tintin-images

EXPOSE $QCON_PORT

CMD ["python", "controller.py"]
