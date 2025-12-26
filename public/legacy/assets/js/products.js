const ENTRUS_PRODUCTS = [
  {
    id: "hoodie_396_guard_the_flame",
    name: "396 Hz Protector Hoodie  Guard the Flame",
    category: "apparel",
    type: "hoodie",
    frequency: 396,
    line: "Seal of Protector",
    tagline: "Guard the Flame.",
    description: "EnTrus 396 Hz Protector hoodie with chest sigil and curved back text. Burnt copper tones, matte cotton blend, slim athletic fit.",
    price: 79.00,
    currency: "USD",
    image: "assets/generated/hoodie_396_guard_the_flame.png",
    status: "active"
  },
  {
    id: "hoodie_528_live_in_rhythm",
    name: "528 Hz Flow Hoodie  Live in Rhythm",
    category: "apparel",
    type: "hoodie",
    frequency: 528,
    line: "Seal of Flow",
    tagline: "Live in Rhythm.",
    description: "Morning Gold and Sage Mist hoodie with Flow spiral sigil. Relaxed street fit with matte-gold EnTrus watermark.",
    price: 79.00,
    currency: "USD",
    image: "assets/generated/hoodie_528_live_in_rhythm.png",
    status: "active"
  },
  {
    id: "hoodie_639_fuel_the_bond",
    name: "639 Hz Drive Hoodie  Fuel the Bond",
    category: "apparel",
    type: "hoodie",
    frequency: 639,
    line: "Seal of Drive",
    tagline: "Fuel the Bond.",
    description: "Sandstone Taupe hoodie with golden tri-ring Drive sigil. Connection-focused tone, matte cotton, everyday wearable.",
    price: 79.00,
    currency: "USD",
    image: "assets/generated/hoodie_639_fuel_the_bond.png",
    status: "active"
  },
  {
    id: "hoodie_852_reveal_the_light",
    name: "852 Hz Seer Hoodie  Reveal the Light",
    category: "apparel",
    type: "hoodie",
    frequency: 852,
    line: "Seal of Seer",
    tagline: "Reveal the Light.",
    description: "White Clarity hoodie with Gold Eclipse gradient and open-eye Seer sigil. Visionary oversized fit.",
    price: 82.00,
    currency: "USD",
    image: "assets/generated/hoodie_852_reveal_the_light.png",
    status: "active"
  },
  {
    id: "shoe_fusion_nightline",
    name: "EnTrus Fusion Nightline Shoe",
    category: "footwear",
    type: "shoe",
    frequency: 0,
    line: "Fusion",
    tagline: "Move between worlds.",
    description: "Fusion shoe with dual-plane sigil logic and soft cream / blue / fusion black palette. Nightlife-ready comfort.",
    price: 110.00,
    currency: "USD",
    image: "assets/generated/shoe_fusion_nightline.png",
    status: "active"
  }
];

const ENTRUS_BRACELETS = [
  {
    id: "bracelet_396_protector",
    name: "396 Hz Protector Bracelet",
    category: "bracelet",
    frequency: 396,
    line: "Seal of Protector",
    tagline: "Guard the Flame.",
    description: "Matte dark stone beads with ember accents following the EnTrus Bead Placement Code. Grounding and protective tone.",
    price: 55.00,
    currency: "USD",
    image: "assets/generated/bracelet_396_protector.png",
    status: "active"
  },
  {
    id: "bracelet_528_flow",
    name: "528 Hz Flow Bracelet",
    category: "bracelet",
    frequency: 528,
    line: "Seal of Flow",
    tagline: "Live in Rhythm.",
    description: "Forest and sage bead gradient with golden flow core bead. Designed for movement and ease.",
    price: 55.00,
    currency: "USD",
    image: "assets/generated/bracelet_528_flow.png",
    status: "active"
  },
  {
    id: "bracelet_639_drive",
    name: "639 Hz Drive Bracelet",
    category: "bracelet",
    frequency: 639,
    line: "Seal of Drive",
    tagline: "Fuel the Bond.",
    description: "Tri-tone bead weave echoing connection and collaboration. Balanced symmetry per EnTrus bead logic.",
    price: 55.00,
    currency: "USD",
    image: "assets/generated/bracelet_639_drive.png",
    status: "active"
  },
  {
    id: "bracelet_852_seer",
    name: "852 Hz Seer Bracelet",
    category: "bracelet",
    frequency: 852,
    line: "Seal of Seer",
    tagline: "Reveal the Light.",
    description: "White and gold bead pattern with Seer pulse spacing. Vision-focused, light-forward layout.",
    price: 59.00,
    currency: "USD",
    image: "assets/generated/bracelet_852_seer.png",
    status: "active"
  },
  {
    id: "bracelet_transfusion_neutral",
    name: "Transfusion Bracelet  Neutral Gradient",
    category: "bracelet",
    frequency: 0,
    line: "Transfusion",
    tagline: "Bridge the frequencies.",
    description: "Neutral  yellow  green gradient bracelet with EnTrus seal bead, matching your Transfusion design language.",
    price: 62.00,
    currency: "USD",
    image: "assets/generated/bracelet_transfusion_neutral.png",
    status: "active"
  }
];

function createProductCard(p) {
  const card = document.createElement("article");
  card.className = "entrus-product-card";
  const freqLabel = p.frequency && p.frequency !== 0 ? `${p.frequency} Hz` : "";
  card.innerHTML = `
    <div class="entrus-product-image">
      <img src="${p.image}" alt="${p.name}" loading="lazy" />
    </div>
    <div class="entrus-product-body">
      <div class="entrus-product-line">${p.line}</div>
      <h3 class="entrus-product-name">${p.name}</h3>
      <p class="entrus-product-tagline">${p.tagline}</p>
      <p class="entrus-product-desc">${p.description}</p>
      <div class="entrus-product-meta">
        ${freqLabel ? `<span class="entrus-product-freq">${freqLabel}</span>` : ""}
        <span class="entrus-product-price">$${p.price.toFixed(2)}</span>
      </div>
    </div>
  `;
  return card;
}

function renderGrid(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  items.forEach(p => {
    const card = createProductCard(p);
    container.appendChild(card);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const apparelGrid = document.getElementById("apparel-grid");
  if (apparelGrid) {
    const items = ENTRUS_PRODUCTS.filter(
      p => p.category === "apparel" || p.category === "footwear"
    );
    renderGrid("apparel-grid", items);
  }

  const braceletGrid = document.getElementById("bracelet-grid");
  if (braceletGrid) {
    renderGrid("bracelet-grid", ENTRUS_BRACELETS);
  }
});
