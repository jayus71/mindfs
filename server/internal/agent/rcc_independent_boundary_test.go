//go:build linux

package agent

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRCCIndependentProbeDoesNotOpenProject(t *testing.T) {
	root := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", root)
	capture := filepath.Join(root, "unexpected-execution")
	command := filepath.Join(root, "rcc")
	if err := os.WriteFile(command, []byte("#!/bin/sh\ntouch '"+capture+"'\nexit 99\n"), 0700); err != nil {
		t.Fatal(err)
	}
	def := Definition{Name: "rcc-independent", Protocol: Protocol("rcc"), Command: command, Args: []string{"--confirm-project"}}
	cfg := Config{Agents: []Definition{def}}
	pool := NewPool(cfg)
	defer pool.CloseAll()
	prober := NewProber(&cfg, pool, time.Hour)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	status := prober.ProbeOne(ctx, def.Name)
	if !status.Installed || !status.Available {
		t.Fatalf("installed RCC probe status: %+v", status)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatalf("global RCC probe executed project command: %v", err)
	}
	if importer, err := NewExternalSessionImporter(def); err == nil || importer != nil {
		t.Fatalf("RCC local transcript importer: %v, %v", importer, err)
	}
}
