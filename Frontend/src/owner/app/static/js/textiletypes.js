const TEXTILE_ORDER = ["pina", "jusi", "cocoon"];

const TEXTILES = {
  pina: {
    title: "Piña",
    description:
      "A traditional textile associated with Barong Tagalog and known for its delicate appearance and fine texture.",
    material: "Pineapple leaf fibers",
    origin: "Philippines",
    uses: "Formal Barong Tagalog, ceremonial wear",
    characteristics: "Fine, Sheer, Lustrous",
    images: ["images/textiles/pina.png"],
  },
  jusi: {
    title: "Jusi",
    description:
      "A lightweight textile commonly associated with Barong Tagalog garments and formal wear.",
    material: "Silk / pineapple blend",
    origin: "Philippines",
    uses: "Everyday formal Barong, celebrations",
    characteristics: "Lightweight, Slightly sheer",
    images: ["images/textiles/jusi.png"],
  },
  cocoon: {
    title: "Cocoon",
    description:
      "A lightweight silk fabric with a smooth texture and subtle sheen, giving the Barong Tagalog an elegant and refined appearance.",
    material: "Silk cocoon fibers",
    origin: "Philippines",
    uses: "Elegant Barong Tagalog",
    characteristics: "Smooth, Soft sheen",
    images: ["images/textiles/cocoon.jpg"],
  },
};

let activeIndex = 0;

function staticUrl(path) {
  const base = document.body?.dataset?.staticRoot || "/static/";
  return base.replace(/\/?$/, "/") + path.replace(/^\//, "");
}

function renderDots() {
  const dots = document.getElementById("textileDots");
  if (!dots) return;
  dots.innerHTML = TEXTILE_ORDER.map((_, i) => {
    const on = i === activeIndex ? " is-on" : "";
    return `<button type="button" class="textile-dot${on}" data-index="${i}" aria-label="Textile ${i + 1}"></button>`;
  }).join("");
  dots.querySelectorAll(".textile-dot").forEach((btn) => {
    btn.addEventListener("click", () => openTextileAt(Number(btn.dataset.index)));
  });
}

function fillModal(key) {
  const data = TEXTILES[key];
  if (!data) return;
  const idx = TEXTILE_ORDER.indexOf(key);
  activeIndex = idx < 0 ? 0 : idx;

  document.getElementById("modalTitle").textContent = data.title;
  document.getElementById("modalDescription").textContent = data.description;
  document.getElementById("modalMaterial").textContent = data.material;
  document.getElementById("modalOrigin").textContent = data.origin;
  document.getElementById("modalUses").textContent = data.uses;
  document.getElementById("modalCharacteristics").textContent = data.characteristics;
  document.getElementById("modalIndex").textContent = `${activeIndex + 1} OF ${TEXTILE_ORDER.length}`;

  const img = document.getElementById("modalImage");
  img.src = staticUrl(data.images[0]);
  img.alt = data.title;

  renderDots();
}

function openTextileAt(index) {
  const safe = ((index % TEXTILE_ORDER.length) + TEXTILE_ORDER.length) % TEXTILE_ORDER.length;
  openTextileModal(TEXTILE_ORDER[safe]);
}

function openTextileModal(key) {
  const data = TEXTILES[key];
  if (!data) return;
  fillModal(key);
  const modal = document.getElementById("textileModal");
  modal.hidden = false;
  modal.classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeTextileModal() {
  const modal = document.getElementById("textileModal");
  modal.hidden = true;
  modal.classList.remove("open");
  document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".textile-card[data-textile]").forEach((card) => {
    card.addEventListener("click", () => openTextileModal(card.dataset.textile));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openTextileModal(card.dataset.textile);
      }
    });
  });

  document.getElementById("closeTextileModal")?.addEventListener("click", closeTextileModal);
  document.getElementById("textilePrev")?.addEventListener("click", () => openTextileAt(activeIndex - 1));
  document.getElementById("textileNext")?.addEventListener("click", () => openTextileAt(activeIndex + 1));
  document.getElementById("textileModal")?.addEventListener("click", (event) => {
    if (event.target.id === "textileModal") closeTextileModal();
  });
  document.addEventListener("keydown", (event) => {
    const modal = document.getElementById("textileModal");
    if (!modal || modal.hidden) return;
    if (event.key === "Escape") closeTextileModal();
    if (event.key === "ArrowLeft") openTextileAt(activeIndex - 1);
    if (event.key === "ArrowRight") openTextileAt(activeIndex + 1);
  });
});
