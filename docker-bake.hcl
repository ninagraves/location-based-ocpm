variable "VERSION" {
  default = "latest"
}

variable "REPO" {
  default = "ocelescope"
}

group "default" {
  targets = ["backend", "frontend"]
}

target "backend" {
  dockerfile = "./docker/backend.Dockerfile"
  contexts = {
    data = "./data"
  }

  tags = [
    "${REPO}-backend:${VERSION}",
    "${REPO}-backend:latest",
  ]
}

target "frontend" {
  dockerfile = "./docker/frontend.Dockerfile"

  args = {
    NEXT_PUBLIC_APP_VERSION = "${VERSION}"
  }

  tags = [
    "${REPO}-frontend:${VERSION}",
    "${REPO}-frontend:latest",
  ]
}
