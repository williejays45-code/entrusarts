(function () {
  function persistOptions(productId, size, color) {
    try {
      const key = 'entrus_last_options_' + productId;
      const payload = { productId, size: size || null, color: color || null, ts: Date.now() };
      localStorage.setItem(key, JSON.stringify(payload));
      console.log('[EnTrus] Saved options for', productId, payload);
    } catch (e) {
      console.warn('[EnTrus] Failed to persist options', e);
    }
  }

  function initProductOptions() {
    const optionBlocks = document.querySelectorAll('.ea-product-options');
    if (!optionBlocks.length) return;

    optionBlocks.forEach(block => {
      const productId = block.getAttribute('data-product-id');
      if (!productId) return;

      const sizeSelect  = block.querySelector('.ea-select-size');
      const colorSelect = block.querySelector('.ea-select-color');
      const btn = document.querySelector('.ea-btn-primary[data-product-id="' + productId + '"]');

      function getCurrent() {
        const size  = sizeSelect  ? sizeSelect.value  : null;
        const color = colorSelect ? colorSelect.value : null;
        return { size, color };
      }

      function restore() {
        try {
          const key = 'entrus_last_options_' + productId;
          const raw = localStorage.getItem(key);
          if (!raw) return;
          const data = JSON.parse(raw);
          if (sizeSelect && data.size)  sizeSelect.value  = data.size;
          if (colorSelect && data.color) colorSelect.value = data.color;
        } catch (e) {
          console.warn('[EnTrus] Failed to restore options', e);
        }
      }

      restore();

      if (sizeSelect)  sizeSelect.addEventListener('change', () => {
        const cur = getCurrent();
        persistOptions(productId, cur.size, cur.color);
      });

      if (colorSelect) colorSelect.addEventListener('change', () => {
        const cur = getCurrent();
        persistOptions(productId, cur.size, cur.color);
      });

      if (btn) {
        btn.addEventListener('click', () => {
          const cur = getCurrent();
          persistOptions(productId, cur.size, cur.color);
        });
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProductOptions);
  } else {
    initProductOptions();
  }
})();
