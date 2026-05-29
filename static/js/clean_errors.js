// ── CLEAR ERRORS ON NEW FILE SELECTION ──────────────────────────────────────
const fileInput = document.getElementById("file");
const errorBox  = document.querySelector(".invalid-feedback");

if (fileInput) {
    fileInput.addEventListener("change", function () {
        fileInput.classList.remove("is-invalid");
        if (errorBox) errorBox.style.display = "none";
    });
}

// ── CLEAR FILE INPUT ON PAGE RELOAD (prevents POST resubmission) ─────────────
window.addEventListener("load", function () {
    if (performance.navigation.type === 1) {
        if (fileInput) fileInput.value = "";
    }
});

// ════════════════════════════════════════════════════════════════════════════
// FORM SUBMISSION + REAL PROGRESS POLLING
// ════════════════════════════════════════════════════════════════════════════
const form            = document.getElementById("convert-form");
const submitBtn       = document.getElementById("submit-btn");
const progressSection = document.getElementById("progress-section");
const progressBar     = document.getElementById("progress-bar");
const progressLabel   = document.getElementById("progress-label");

let _pollInterval = null;

function showProgress() {
    progressBar.style.transition = "none";
    progressBar.style.width      = "0%";
    progressLabel.textContent    = "Starting…";
    progressSection.style.display = "block";
    submitBtn.disabled = true;
}

function updateProgress(done, total) {
    if (total > 0) {
        const pct = (done / total) * 100;
        progressBar.style.transition = "width 0.4s ease";
        progressBar.style.width      = pct.toFixed(1) + "%";
        progressLabel.textContent    = "Processing event " + done + " of " + total + "…";
    } else {
        progressLabel.textContent = "Processing…";
    }
}

function finishProgress() {
    progressBar.style.transition = "width 0.3s ease";
    progressBar.style.width      = "100%";
    progressLabel.textContent    = "Done!";
    setTimeout(function () {
        progressSection.style.display = "none";
        progressBar.style.transition  = "none";
        progressBar.style.width       = "0%";
        submitBtn.disabled = false;
        if (fileInput) fileInput.value = "";
    }, 800);
}

function abortProgress(message) {
    if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
    progressSection.style.display = "none";
    progressBar.style.transition  = "none";
    progressBar.style.width       = "0%";
    submitBtn.disabled = false;
    if (message) alert(message);
}

if (form) {
    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        // Stop any previous polling just in case
        if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }

        showProgress();

        let jobId;
        try {
            const response      = await fetch("/", { method: "POST", body: new FormData(form) });
            const contentType   = response.headers.get("Content-Type") || "";

            if (!contentType.includes("application/json")) {
                // Validation error — Flask returned an HTML page
                abortProgress();
                const html = await response.text();
                document.open(); document.write(html); document.close();
                return;
            }

            const data = await response.json();
            if (data.error || !data.job_id) {
                abortProgress("Error: " + (data.error || "Unknown error"));
                return;
            }
            jobId = data.job_id;

        } catch (err) {
            abortProgress("Network error: " + err.message);
            return;
        }

        // Poll /progress/:jobId every 500 ms
        _pollInterval = setInterval(async function () {
            try {
                const prog = await fetch("/progress/" + jobId).then(r => r.json());

                if (prog.status === "done") {
                    clearInterval(_pollInterval);
                    _pollInterval = null;
                    finishProgress();
                    // Trigger download via hidden link
                    const a = document.createElement("a");
                    a.href     = "/download/" + jobId;
                    a.download = "";
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);

                } else if (prog.status === "error") {
                    clearInterval(_pollInterval);
                    _pollInterval = null;
                    abortProgress("Conversion error: " + (prog.error || "unknown"));

                } else {
                    updateProgress(prog.progress, prog.total);
                }

            } catch (err) {
                clearInterval(_pollInterval);
                _pollInterval = null;
                abortProgress("Network error while polling: " + err.message);
            }
        }, 500);
    });
}

// ════════════════════════════════════════════════════════════════════════════
// SETTINGS MODAL — multi-URL management
// ════════════════════════════════════════════════════════════════════════════

// Current config kept in memory while the modal is open
let _currentConfig = null;

// ── OPEN ─────────────────────────────────────────────────────────────────────
async function openSettings() {
    const data = await fetch("/get_settings").then(r => r.json());
    _currentConfig = data;
    renderUrlList(data);
    document.getElementById("settingsModal").style.display = "flex";
}

// ── CLOSE ────────────────────────────────────────────────────────────────────
function closeSettings() {
    document.getElementById("settingsModal").style.display = "none";
    document.getElementById("new-url-input").value = "";
    _currentConfig = null;
}

// Close modal when clicking the backdrop
document.getElementById("settingsModal").addEventListener("click", function (e) {
    if (e.target === this) closeSettings();
});

// ── RENDER URL LIST ──────────────────────────────────────────────────────────
function renderUrlList(config) {
    const list   = document.getElementById("url-list");
    const saved  = config.saved_urls  || [];
    const active = config.RPC_SERVER_URL || "";

    if (saved.length === 0) {
        list.innerHTML = '<p class="text-muted small">No saved servers. Add one below.</p>';
        return;
    }

    list.innerHTML = "";

    saved.forEach(function (url) {
        const isActive = (url === active);

        const row = document.createElement("div");
        row.className = "d-flex align-items-center gap-2 mb-2 p-2 rounded border "
                      + (isActive ? "border-primary bg-light" : "border-secondary-subtle");

        // URL text
        const span = document.createElement("span");
        span.className  = "flex-grow-1 url-row";
        span.textContent = url;
        row.appendChild(span);

        // "Active" badge OR "Use" button
        if (isActive) {
            const badge = document.createElement("span");
            badge.className   = "badge flex-shrink-0";
            badge.style.backgroundColor = "#003366";
            badge.textContent = "Active";
            row.appendChild(badge);
        } else {
            const useBtn = document.createElement("button");
            useBtn.className   = "btn btn-sm btn-outline-primary flex-shrink-0";
            useBtn.textContent = "Use";
            useBtn.onclick     = () => setActiveUrl(url);
            row.appendChild(useBtn);
        }

        // Delete button
        const delBtn = document.createElement("button");
        delBtn.className   = "btn btn-sm btn-outline-danger flex-shrink-0";
        delBtn.textContent = "✕";
        delBtn.onclick     = () => deleteUrl(url);
        row.appendChild(delBtn);

        list.appendChild(row);
    });
}

// ── SET ACTIVE URL ───────────────────────────────────────────────────────────
async function setActiveUrl(url) {
    const res  = await fetch("/update_settings", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ action: "set_active", url }),
    });
    const data = await res.json();
    if (data.status === "ok") {
        _currentConfig = data.config;
        renderUrlList(data.config);
    }
}

// ── ADD NEW URL ──────────────────────────────────────────────────────────────
async function addUrl() {
    const input = document.getElementById("new-url-input");
    const url   = input.value.trim();
    if (!url) return;

    const res  = await fetch("/update_settings", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ action: "add", url }),
    });
    const data = await res.json();
    if (data.status === "ok") {
        _currentConfig   = data.config;
        input.value      = "";
        renderUrlList(data.config);
    } else {
        alert(data.message || "Could not add URL.");
    }
}

// Allow pressing Enter in the add field
document.getElementById("new-url-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addUrl(); }
});

// ── DELETE URL ───────────────────────────────────────────────────────────────
async function deleteUrl(url) {
    const res  = await fetch("/update_settings", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ action: "delete", url }),
    });
    const data = await res.json();
    if (data.status === "ok") {
        _currentConfig = data.config;
        renderUrlList(data.config);
    }
}