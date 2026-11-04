const TEXTILES = {
  pina: {
    title: "Piña",
    description:
      "A traditional textile associated with Barong Tagalog and known for its delicate appearance and fine texture.",
    material: "Pineapple leaf fibers",
    origin: "Philippines",
    uses: "Formal Barong Tagalog, ceremonial wear",
    characteristics: "Fine, sheer, lustrous",
    images: ["images/textiles/pina.png"],
  },
  jusi: {
    title: "Jusi",
    description:
      "A lightweight textile commonly associated with Barong Tagalog garments and formal wear.",
    material: "Silk / pineapple blend",
    origin: "Philippines",
    uses: "Everyday formal Barong, celebrations",
    characteristics: "Lightweight, slightly sheer",
    images: ["images/textiles/jusi.png"],
  },
  cocoon: {
    title: "Cocoon",
    description:
      "A lightweight silk fabric with a smooth texture and subtle sheen, giving the Barong Tagalog an elegant and refined appearance.",
    material: "Silk cocoon fibers",
    origin: "Philippines",
    uses: "Elegant Barong Tagalog",
    characteristics: "Smooth, soft sheen",
    images: ["images/textiles/cocoon.jpg"],
  },
  others: {
    title: "Others",
    description:
      "Other textile materials and fabric types that may be associated with traditional Filipino clothing.",
    material: "Mixed / alternative fibers",
    origin: "Various",
    uses: "Traditional and contemporary garments",
    characteristics: "Varies by fabric",
    images: ["images/textiles/others.png", "images/textiles/others.jpg", "images/barong.jpg"],
  },
};

function staticUrl(path) {
  const base = document.body?.dataset?.staticRoot || "/static/";
  return base.replace(/\/?$/, "/") + path.replace(/^\//, "");
}

function openTextileModal(key) {
  const data = TEXTILES[key];
  if (!data) return;
  const modal = document.getElementById("textileModal");
  document.getElementById("modalTitle").textContent = data.title;
  document.getElementById("modalDescription").textContent = data.description;
  document.getElementById("modalMaterial").textContent = data.material;
  document.getElementById("modalOrigin").textContent = data.origin;
  document.getElementById("modalUses").textContent = data.uses;
  document.getElementById("modalCharacteristics").textContent = data.characteristics;
  const images = document.getElementById("modalImages");
  images.innerHTML = "";
  data.images.forEach((src) => {
    const img = document.createElement("img");
    img.src = staticUrl(src);
    img.alt = data.title;
    images.appendChild(img);
  });
  modal.hidden = false;
  modal.classList.add("open");
}

function closeTextileModal() {
  const modal = document.getElementById("textileModal");
  modal.hidden = true;
  modal.classList.remove("open");
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
  document.getElementById("textileModal")?.addEventListener("click", (event) => {
    if (event.target.id === "textileModal") closeTextileModal();
  });
});
