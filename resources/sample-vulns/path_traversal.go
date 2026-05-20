// CWE-22: Path Traversal.
// Deva will flag joining user input to a base path without validation.
// The fix is to canonicalize and reject paths that escape the base dir.

package main

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func serveFileVulnerable(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("file")
	// BAD: ?file=../../etc/passwd reads anywhere on the filesystem
	// the server has access to.
	path := filepath.Join("/var/www/uploads", name)
	data, err := os.ReadFile(path)
	if err != nil {
		http.Error(w, err.Error(), 404)
		return
	}
	w.Write(data)
}

func serveFileSafe(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("file")
	base := "/var/www/uploads"
	full := filepath.Clean(filepath.Join(base, name))
	// The fix: confirm the resolved path is still under base.
	if !strings.HasPrefix(full, base+string(os.PathSeparator)) {
		http.Error(w, "invalid path", 400)
		return
	}
	data, err := os.ReadFile(full)
	if err != nil {
		http.Error(w, err.Error(), 404)
		return
	}
	w.Write(data)
}
