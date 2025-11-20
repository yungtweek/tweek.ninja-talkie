package grpc

import (
	"os"
	"testing"
	"time"

	pb "github.com/yungtweek/talkie/apps/llm-gateway/gen/llm"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
)

// fakeLlmService is a minimal implementation of the LlmServiceServer interface
// used only for wiring tests.
type fakeLlmService struct {
	pb.UnimplementedLlmServiceServer
}

func TestNew_RegistersLlmService(t *testing.T) {
	addr := ":50051"
	s := New(addr, &fakeLlmService{})

	if s == nil {
		t.Fatal("expected non-nil Server from New, got nil")
	}

	if s.addr != addr {
		t.Fatalf("expected addr %q, got %q", addr, s.addr)
	}

	serviceInfo := s.grpcServer.GetServiceInfo()
	if _, ok := serviceInfo["llm.v1.LlmService"]; !ok {
		t.Fatalf("expected llm.v1.LlmService to be registered, but it was not")
	}
}

func TestServer_RunAndGracefulStop(t *testing.T) {
	// Use :0 to let the OS pick an available port.
	s := New("127.0.0.1:0", &fakeLlmService{})

	done := make(chan error, 1)
	go func() {
		done <- s.Run()
	}()

	// Give the server a brief moment to start.
	time.Sleep(100 * time.Millisecond)

	// Request a graceful stop and ensure Run returns without error.
	s.GracefulStop()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("expected nil error from Run after GracefulStop, got %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("server.Run did not return within timeout after GracefulStop")
	}
}

func TestMain(m *testing.M) {
	if err := logger.Init(); err != nil {
		panic(err)
	}
	defer logger.Sync()
	os.Exit(m.Run())
}
