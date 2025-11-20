package grpc

import (
	"net"

	pb "github.com/yungtweek/talkie/apps/llm-gateway/gen/llm"
	"github.com/yungtweek/talkie/apps/llm-gateway/internal/logger"
	"go.uber.org/zap"
	ggrpc "google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// Server wraps a gRPC server and its listen address.
type Server struct {
	addr       string
	grpcServer *ggrpc.Server
}

// New creates a new gRPC server for the LlmService at the given address.
// Example addr: ":50051".
func New(addr string, llmService pb.LlmServiceServer) *Server {
	s := &Server{
		addr:       addr,
		grpcServer: ggrpc.NewServer(),
	}

	pb.RegisterLlmServiceServer(s.grpcServer, llmService)
	reflection.Register(s.grpcServer)

	return s
}

// Run starts listening on the configured address and serves the gRPC server.
// This call is blocking until the server stops or returns an error.
func (s *Server) Run() error {
	lis, err := net.Listen("tcp", s.addr)
	if err != nil {
		logger.Log.Error("failed to listen for gRPC server",
			zap.String("addr", s.addr),
			zap.Error(err),
		)
		return err
	}

	logger.Log.Info("starting gRPC server",
		zap.String("addr", s.addr),
	)

	if err := s.grpcServer.Serve(lis); err != nil {
		logger.Log.Error("gRPC server stopped with error", zap.Error(err))
		return err
	}

	logger.Log.Info("gRPC server stopped gracefully")
	return nil
}

// GracefulStop gracefully stops the underlying gRPC server.
func (s *Server) GracefulStop() {
	logger.Log.Info("gracefully stopping gRPC server",
		zap.String("addr", s.addr),
	)
	s.grpcServer.GracefulStop()
}
