// Shows data-bs-title on hover and focus for anything marked data-bs-toggle="tooltip", as
// seating does. A file, not inline script, because the Content-Security-Policy blocks that.
document.addEventListener("DOMContentLoaded", () => {
  if (window.bootstrap) {
    new bootstrap.Tooltip(document.body, { selector: '[data-bs-toggle="tooltip"]' });
  }
});
