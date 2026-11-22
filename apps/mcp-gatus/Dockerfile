# gatus-mcp at a pinned commit on digest-pinned bases (upstream's Dockerfile floats them).
FROM golang:1.26-alpine@sha256:ecb67f987aa1a57794c91d19ade7ae0209f2f0f5496aaef9e6ae85ddf92d02ab AS build

ARG GATUS_MCP_COMMIT=4c7ed599114d920437bd37f6590744573e361e46

# The Go module proxy and checksum database verify the source of the pinned commit.
RUN CGO_ENABLED=0 GOTOOLCHAIN=auto GOBIN=/out \
    go install -ldflags="-s -w" "github.com/adambenhassen/gatus-mcp/cmd/gatus-mcp@${GATUS_MCP_COMMIT}"

# Static binary, plain-HTTP upstream: no CA bundle or libc needed.
FROM scratch

LABEL name="mcp-gatus" version="0.0.0+4c7ed599"
COPY --from=build /out/gatus-mcp /gatus-mcp
USER 65532:65532
EXPOSE 3000
ENTRYPOINT ["/gatus-mcp"]
