#!/bin/sh
set -eu

# Redis keeps ntopng users and preferences: the bind-mounted host directory
# must belong to the image's redis user or every write fails after a BGSAVE error.
chown -R redis:redis /var/lib/redis
exec /run.sh /etc/ntopng/nabla.conf
