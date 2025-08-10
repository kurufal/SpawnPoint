const pane = document.getElementById('terminal-pane');
const toggle = document.getElementById('toggle-terminal');
const closeBtn = document.getElementById('close-terminal');

function setPane(expanded) {
  pane.classList.toggle('expanded', expanded);
  pane.classList.toggle('collapsed', !expanded);
}

toggle?.addEventListener('click', () => setPane(!pane.classList.contains('expanded')));
closeBtn?.addEventListener('click', () => setPane(false));

// Start collapsed
setPane(false);
