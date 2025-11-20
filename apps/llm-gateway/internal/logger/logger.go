package logger

import (
	"go.uber.org/zap"
)

var Log *zap.Logger

func Init() error {
	l, err := zap.NewProduction() // JSON structured logging
	if err != nil {
		return err
	}
	Log = l
	return nil
}

func Sync() {
	if Log != nil {
		_ = Log.Sync()
	}
}
