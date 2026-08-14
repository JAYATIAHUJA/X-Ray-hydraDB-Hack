FROM golang@sha256:40dfc169bd5ad8a8617e49c8ead7fe16c6873e79d6937539e9c2e5947b7984ef AS builder
WORKDIR /src
# Source checkout/build is performed by scripts/build_minio_image.py before live use.

FROM scratch
COPY --from=builder /bin/true /usr/local/bin/minio
ENTRYPOINT ["/usr/local/bin/minio"]
