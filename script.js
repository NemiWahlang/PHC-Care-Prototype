// script.js
// ---------
// LEARNING NOTE: this file talks to the backend using fetch(), which
// sends a real HTTP request and gives back a Promise. `await` just
// means "pause this function until the response arrives" -- it reads
// top-to-bottom like normal code instead of nesting callbacks.

const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("villageInput");
const phcListEl = document.getElementById("phcList");

function addMessage(text, sender) {
  const div = document.createElement("div");
  div.className = `msg ${sender}`;
  div.textContent = text; // textContent, not innerHTML: never render user input as HTML
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); // stop the browser from reloading the page
  const village = input.value.trim();
  if (!village) return;

  addMessage(village, "user");
  input.value = "";

  try {
    const res = await fetch(`/api/status/${encodeURIComponent(village)}`);

    if (!res.ok) {
      // Our FastAPI backend sends 404s with a helpful {"detail": "..."}
      // body when nothing matches closely enough -- show that message
      // directly instead of a generic error.
      const err = await res.json();
      addMessage(err.detail || "Couldn't find that village.", "bot");
      return;
    }

    const data = await res.json();
    const reply =
      data.status === "Active"
        ? `${data.doctor_name} is currently checked in at ${data.village_name} PHC.`
        : `No doctor is currently checked in at ${data.village_name} PHC.`;
    addMessage(reply, "bot");
  } catch (err) {
    // This fires if the backend isn't running at all, not just a 404.
    addMessage("Connection error — is the server running?", "bot");
  }
});

async function loadPhcs() {
  const res = await fetch("/api/phcs");
  const phcs = await res.json();

  phcListEl.innerHTML = "";
  phcs.forEach((phc) => {
    const li = document.createElement("li");
    li.className = "phc-row";
    li.innerHTML = `
      <div class="phc-info">
        <span class="phc-name">${phc.village_name}</span>
        <span class="phc-district">${phc.district}</span>
      </div>
      <span class="pill ${phc.status.toLowerCase()}">${phc.status}</span>
      <button class="toggle-btn" data-id="${phc.phc_id}" type="button">Toggle</button>
    `;
    phcListEl.appendChild(li);
  });
}

// Event delegation: one listener on the parent list catches clicks on
// any toggle button, including ones added after the page first loads.
phcListEl.addEventListener("click", async (event) => {
  if (!event.target.classList.contains("toggle-btn")) return;
  const phcId = event.target.dataset.id;
  await fetch(`/api/toggle/${phcId}`, { method: "POST" });
  loadPhcs(); // refresh the panel so the pill color updates immediately
});

loadPhcs();
