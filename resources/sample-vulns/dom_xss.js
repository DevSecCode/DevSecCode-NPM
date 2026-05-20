// CWE-79: DOM-based XSS.
// Deva will flag the unsanitized assignment of user input to innerHTML.
// The fix is to use textContent or a sanitization library.

function renderGreetingVulnerable() {
    const params = new URLSearchParams(window.location.search);
    const name = params.get('name');
    // BAD: a URL like ?name=<img onerror=alert(1) src=x> executes JS.
    document.getElementById('greeting').innerHTML = `Hello, ${name}!`;
}

function renderGreetingSafe() {
    const params = new URLSearchParams(window.location.search);
    const name = params.get('name');
    // textContent escapes everything — no parsed HTML, no script execution.
    document.getElementById('greeting').textContent = `Hello, ${name}!`;
}
