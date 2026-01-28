#!/bin/bash
# Test script for Docker Compose setup
# Usage: ./test-docker-compose.sh

set -e

echo "======================================"
echo "Docker Compose Validation Test"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function for test results
test_passed() {
    echo -e "${GREEN}✅ PASSED:${NC} $1"
    ((TESTS_PASSED++))
}

test_failed() {
    echo -e "${RED}❌ FAILED:${NC} $1"
    ((TESTS_FAILED++))
}

test_warning() {
    echo -e "${YELLOW}⚠️  WARNING:${NC} $1"
}

# Test 1: Check Docker is installed
echo "Test 1: Checking Docker installation..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    test_passed "Docker is installed: $DOCKER_VERSION"
else
    test_failed "Docker is not installed"
    exit 1
fi
echo ""

# Test 2: Check Docker Compose is installed
echo "Test 2: Checking Docker Compose installation..."
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version)
    test_passed "Docker Compose is installed: $COMPOSE_VERSION"
else
    test_failed "Docker Compose is not installed"
    exit 1
fi
echo ""

# Test 3: Validate docker-compose.yml syntax
echo "Test 3: Validating docker-compose.yml syntax..."
if docker compose config --quiet; then
    test_passed "docker-compose.yml syntax is valid"
else
    test_failed "docker-compose.yml has syntax errors"
fi
echo ""

# Test 4: Validate production compose file
echo "Test 4: Validating production compose configuration..."
if docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet; then
    test_passed "Production compose configuration is valid"
else
    test_failed "Production compose configuration has errors"
fi
echo ""

# Test 5: Check for required files
echo "Test 5: Checking for required files..."
REQUIRED_FILES=("docker-compose.yml" "Dockerfile" ".env.example" "nginx.conf")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        test_passed "Found $file"
    else
        test_failed "Missing $file"
    fi
done
echo ""

# Test 6: Check for .env file
echo "Test 6: Checking environment configuration..."
if [ -f ".env" ]; then
    test_passed ".env file exists"
else
    test_warning ".env file not found. Creating from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        test_passed "Created .env from .env.example"
    else
        test_failed ".env.example not found"
    fi
fi
echo ""

# Test 7: Validate Dockerfile
echo "Test 7: Validating Dockerfile..."
if [ -f "Dockerfile" ]; then
    # Check if hadolint is available
    if command -v hadolint &> /dev/null; then
        if hadolint Dockerfile; then
            test_passed "Dockerfile passes hadolint checks"
        else
            test_warning "Dockerfile has hadolint warnings"
        fi
    else
        test_warning "hadolint not installed, skipping Dockerfile linting"
    fi
else
    test_failed "Dockerfile not found"
fi
echo ""

# Test 8: Check service definitions
echo "Test 8: Checking service definitions..."
SERVICES=$(docker compose config --services)
EXPECTED_SERVICES=("web" "postgres" "redis" "nginx")
for service in "${EXPECTED_SERVICES[@]}"; do
    if echo "$SERVICES" | grep -q "$service"; then
        test_passed "Service $service is defined"
    else
        test_failed "Service $service is not defined"
    fi
done
echo ""

# Test 9: Check network configuration
echo "Test 9: Checking network configuration..."
if docker compose config | grep -q "networks:"; then
    test_passed "Networks are defined"
else
    test_failed "No networks defined"
fi
echo ""

# Test 10: Check volume configuration
echo "Test 10: Checking volume configuration..."
if docker compose config | grep -q "volumes:"; then
    test_passed "Volumes are defined"
else
    test_failed "No volumes defined"
fi
echo ""

# Test 11: Check health checks
echo "Test 11: Checking health check definitions..."
if docker compose config | grep -q "healthcheck:"; then
    test_passed "Health checks are defined"
else
    test_warning "No health checks defined"
fi
echo ""

# Summary
echo "======================================"
echo "Test Summary"
echo "======================================"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo ""
    echo "You can now start the services with:"
    echo "  docker compose up -d"
    exit 0
else
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo "Please fix the issues before starting the services."
    exit 1
fi
