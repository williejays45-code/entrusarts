(function () {
  function buildSummary(cartItems, catalog) {
    var bands = {};
    cartItems.forEach(function (ci) {
      var match = null;
      for (var i = 0; i < catalog.length; i++) {
        if (catalog[i].id === ci.id) {
          match = catalog[i];
          break;
        }
      }
      var band = (match && match.guardianBand) ? match.guardianBand : "Unmapped";
      if (!bands[band]) {
        bands[band] = { qty: 0, items: [] };
      }
      bands[band].qty += ci.qty || 1;
      bands[band].items.push({
        id: ci.id,
        name: ci.name || (match ? match.name : ci.id),
        qty: ci.qty || 1
      });
    });
    return bands;
  }

  function renderGuardianOverlay() {
    var root = document.getElementById("guardian-alignment-summary");
    if (!root) return;
    if (!window.EnTrusCart || !window.EnTrusCatalog) {
      root.innerHTML = "<p class='guardian-summary-empty'>Cart or catalog unavailable.</p>";
      return;
    }

    var cartItems = window.EnTrusCart.getItems();
    if (!cartItems.length) {
      root.innerHTML = "<p class='guardian-summary-empty'>No items in the cart yet. Alignment summary appears once you add at least one piece.</p>";
      return;
    }

    var summary = buildSummary(cartItems, window.EnTrusCatalog);
    var bandsOrder = ["Protector", "Flow", "Drive", "Expression", "Seer", "Bracelet Core", "Outer Layer", "Path Layer", "Core Layer", "Growth Line", "Fusion Line", "Generic", "Unmapped"];

    var frag = document.createDocumentFragment();

    bandsOrder.forEach(function (band) {
      if (!summary[band]) return;
      var block = document.createElement("div");
      block.className = "guardian-band-row";
      var qty = summary[band].qty;
      var names = summary[band].items.map(function (x) {
        return x.name + " " + x.qty;
      }).join(", ");

      block.innerHTML =
        "<div class='guardian-band-label'>" + band + "</div>" +
        "<div class='guardian-band-qty'>" + qty + " piece" + (qty > 1 ? "s" : "") + "</div>" +
        "<div class='guardian-band-items'>" + names + "</div>";

      frag.appendChild(block);
    });

    root.innerHTML = "";
    root.appendChild(frag);
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderGuardianOverlay();
  });

  // Optional: expose for manual refresh (if cart changes later)
  window.EnTrusGuardianOverlay = {
    refresh: renderGuardianOverlay
  };
})();
