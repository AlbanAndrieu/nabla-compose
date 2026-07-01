#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
print_info() {
  echo -e "$YELLOW[INFO]$NC $1"
}
print_success() {
  echo -e "$GREEN[SUCCESS]$NC $1"
}
print_error() {
  echo -e "$RED[ERROR]$NC $1"
}
if [ $# -eq 0 ]; then
  print_error "No container name provided"
  echo "Usage: $0 <container_name>"
  exit 1
fi
CONTAINER_NAME=$1
if ! docker ps | grep -q $CONTAINER_NAME; then
  print_error "Container '$CONTAINER_NAME' not found in running containers"
  echo "Running containers:"
  docker ps --format "table {{.Names}}\t{{.Status}}"
  exit 1
fi
print_info "Attempting to stop container '$CONTAINER_NAME'..."
if docker stop $CONTAINER_NAME; then
  print_success "Successfully stopped container '$CONTAINER_NAME'"
  exit 0
fi
print_info "Docker stop failed, attempting docker kill..."
if docker kill $CONTAINER_NAME; then
  print_success "Successfully killed container '$CONTAINER_NAME'"
  exit 0
fi
print_info "Docker kill failed, attempting to kill containerd-shim process..."
CONTAINER_ID=$(docker ps | grep $CONTAINER_NAME | awk '{print $1}')
if [ -z "$CONTAINER_ID" ]; then
  print_error "Could not find container ID for '$CONTAINER_NAME'"
  exit 1
fi
SHIM_PID=$(sudo ps awx | grep containerd-shim | grep $CONTAINER_ID | awk '{print $1}')
if [ -z "$SHIM_PID" ]; then
  print_error "Could not find containerd-shim process"
  exit 1
fi
print_info "Killing process $SHIM_PID..."
sudo kill -9 $SHIM_PID
print_info "Process killed. Checking container status..."
sleep 2
if ! docker ps | grep -q $CONTAINER_NAME; then
  print_success "Container '$CONTAINER_NAME' successfully stopped"
else
  print_error "Container '$CONTAINER_NAME' is still running"
  docker ps | grep $CONTAINER_NAME
fi
exit 0
