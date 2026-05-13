// -------------------------------------------------------------
// 1. CLEAR VALIDATION WHEN A NEW FILE IS SELECTED
// -------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.getElementById("file");
    const errorBox = document.querySelector(".invalid-feedback");

    if (fileInput) {
        fileInput.addEventListener("change", function () {
            fileInput.classList.remove("is-invalid");
            if (errorBox) {
                errorBox.style.display = "none";
            }
        });
    }
});

// -------------------------------------------------------------
// 2. CLEAR ONLY THE FILE INPUT WHEN THE PAGE IS REFRESHED
// -------------------------------------------------------------
window.addEventListener("load", function () {
    if (performance.navigation.type === 1) {
        const fileInput = document.getElementById("file");
        if (fileInput) {
            fileInput.value = "";
        }
    }
});

// -------------------------------------------------------------
// 3. LOAD SERVER SETTINGS WHEN OPENING THE MODAL
// -------------------------------------------------------------
async function openSettings() {
    try {
        const response = await fetch("/get_settings");
        const data = await response.json();

        document.getElementById("rpc_ip").value = data.RPC_SERVER_IP;
        document.getElementById("rpc_port").value = data.RPC_SERVER_PORT;

        document.getElementById("settingsModal").style.display = "flex";
    } catch (err) {
        alert("Error loading settings");
    }
}

function closeSettings() {
    document.getElementById("settingsModal").style.display = "none";
}

// -------------------------------------------------------------
// 4. SAVE SERVER SETTINGS FROM THE MODAL
// -------------------------------------------------------------
async function saveSettings() {
    const ip = document.getElementById("rpc_ip").value;
    const port = document.getElementById("rpc_port").value;

    try {
        const response = await fetch("/update_settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip: ip, port: port })
        });

        const data = await response.json();

        if (data.status === "ok") {
            alert("Settings saved successfully");
            closeSettings();
        } else {
            alert("Error saving settings");
        }

    } catch (err) {
        alert("Error sending settings");
    }
}
