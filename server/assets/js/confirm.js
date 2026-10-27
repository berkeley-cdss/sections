// Asks before submitting a form with data-confirm="<question>". This is a file, not an
// onsubmit= handler, because the Content-Security-Policy blocks inline script.
document.addEventListener("submit", (event) => {
  const question = event.target.dataset.confirm;
  if (question && !confirm(question)) {
    event.preventDefault();
  }
});
