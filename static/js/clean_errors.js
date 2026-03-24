
// This script clears validation errors when the user selects a new file.
// It prevents the red border and error message from persisting unnecessarily.
document.addEventListener("DOMContentLoaded", function () {
  const fileInput = document.getElementById("file");
  const errorBox = document.querySelector(".invalid-feedback");

  // When the user selects a new file, remove previous error indicators
  fileInput.addEventListener("change", function () {
    fileInput.classList.remove("is-invalid");
    if (errorBox) {
      errorBox.style.display = "none";
    }
  });
});
