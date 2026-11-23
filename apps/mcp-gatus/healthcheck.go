// Health probe for the scratch image (no shell): the MCP port accepts a TCP connection.
package main

import (
	"net"
	"os"
	"time"
)

func main() {
	conn, err := net.DialTimeout("tcp", "127.0.0.1:3000", 3*time.Second)
	if err != nil {
		os.Exit(1)
	}
	_ = conn.Close()
}
