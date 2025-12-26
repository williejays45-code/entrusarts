(function () {
  const CART_KEY = 'entrus_cart_v1';

  function loadCart() {
    try {
      const raw = localStorage.getItem(CART_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed;
    } catch (e) {
      console.warn('[EnTrus Cart] Failed to load cart', e);
      return [];
    }
  }

  function saveCart(cart) {
    try {
      localStorage.setItem(CART_KEY, JSON.stringify(cart));
    } catch (e) {
      console.warn('[EnTrus Cart] Failed to save cart', e);
    }
  }

  function getLastOptions(productId) {
    try {
      const key = 'entrus_last_options_' + productId;
      const raw = localStorage.getItem(key);
      if (!raw) return { size: null, color: null };
      const data = JSON.parse(raw);
      return {
        size: data.size || null,
        color: data.color || null
      };
    } catch (e) {
      return { size: null, color: null };
    }
  }

  function addToCart(productId) {
    const titleEl = document.querySelector('.ea-product-title');
    const name = titleEl ? titleEl.textContent.trim() : productId;

    const opts = getLastOptions(productId);
    const size = opts.size;
    const color = opts.color;

    let cart = loadCart();

    // Look for existing line with same id + size + color
    let found = cart.find(item =>
      item.id === productId &&
      item.size === size &&
      item.color === color
    );

    if (found) {
      found.quantity += 1;
    } else {
      cart.push({
        id: productId,
        name: name,
        size: size,
        color: color,
        quantity: 1,
        saved: false
      });
    }

    saveCart(cart);
    renderCartBadge();
    renderCartPanel();
  }

  function toggleSaved(productId, size, color) {
    let cart = loadCart();
    cart = cart.map(item => {
      if (item.id === productId && item.size === size && item.color === color) {
        return Object.assign({}, item, { saved: !item.saved });
      }
      return item;
    });
    saveCart(cart);
    renderCartPanel();
  }

  function removeLine(productId, size, color) {
    let cart = loadCart();
    cart = cart.filter(item =>
      !(item.id === productId && item.size === size && item.color === color)
    );
    saveCart(cart);
    renderCartBadge();
    renderCartPanel();
  }

  function renderCartBadge() {
    const cart = loadCart();
    const totalQty = cart.reduce((sum, item) => sum + (item.quantity || 0), 0);

    let badge = document.getElementById('entrus-cart-badge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'entrus-cart-badge';
      badge.style.position = 'fixed';
      badge.style.right = '16px';
      badge.style.bottom = '16px';
      badge.style.width = '40px';
      badge.style.height = '40px';
      badge.style.borderRadius = '999px';
      badge.style.background = '#111';
      badge.style.color = '#fff';
      badge.style.display = 'flex';
      badge.style.alignItems = 'center';
      badge.style.justifyContent = 'center';
      badge.style.cursor = 'pointer';
      badge.style.fontSize = '14px';
      badge.style.zIndex = '9999';
      badge.style.boxShadow = '0 4px 10px rgba(0,0,0,0.4)';
      badge.title = 'Open cart';

      badge.addEventListener('click', () => {
        const panel = document.getElementById('entrus-cart-panel');
        if (panel) {
          const visible = panel.getAttribute('data-open') === 'true';
          panel.setAttribute('data-open', visible ? 'false' : 'true');
          panel.style.transform = visible ? 'translateX(100%)' : 'translateX(0)';
        }
      });

      document.body.appendChild(badge);
    }

    badge.textContent = totalQty > 9 ? '9+' : String(totalQty);
  }

  function ensureCartPanel() {
    let panel = document.getElementById('entrus-cart-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'entrus-cart-panel';
      panel.setAttribute('data-open', 'false');
      panel.style.position = 'fixed';
      panel.style.top = '0';
      panel.style.right = '0';
      panel.style.width = '320px';
      panel.style.height = '100vh';
      panel.style.background = '#0b0b0b';
      panel.style.color = '#f5f5f5';
      panel.style.boxShadow = '-4px 0 12px rgba(0,0,0,0.6)';
      panel.style.transform = 'translateX(100%)';
      panel.style.transition = 'transform 0.25s ease-out';
      panel.style.zIndex = '9998';
      panel.style.display = 'flex';
      panel.style.flexDirection = 'column';
      panel.style.fontSize = '14px';

      panel.innerHTML = 
        <div style="padding: 12px 16px; border-bottom: 1px solid #333; display:flex; align-items:center; justify-content:space-between;">
          <div style="font-weight:600;">EnTrus Cart</div>
          <button id="entrus-cart-close" style="background:none;border:none;color:#f5f5f5;font-size:18px;cursor:pointer;"></button>
        </div>
        <div id="entrus-cart-body" style="flex:1; overflow-y:auto; padding:12px 16px;"></div>
        <div id="entrus-cart-footer" style="padding:10px 16px; border-top:1px solid #333; font-size:12px; color:#aaa;">
          Local preview only  No payments are processed here.
        </div>
      ;

      document.body.appendChild(panel);

      const closeBtn = panel.querySelector('#entrus-cart-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', () => {
          panel.setAttribute('data-open', 'false');
          panel.style.transform = 'translateX(100%)';
        });
      }
    }
    return panel;
  }

  function renderCartPanel() {
    const panel = ensureCartPanel();
    const body = panel.querySelector('#entrus-cart-body');
    if (!body) return;

    const cart = loadCart();
    if (!cart.length) {
      body.innerHTML = '<p style="color:#aaa;">Cart is empty. Add a piece to see it here.</p>';
      return;
    }

    const lines = cart.map(item => {
      const sizePart  = item.size  ?   Size:  : '';
      const colorPart = item.color ?   Color:  : '';
      const savedTag  = item.saved ? <span style="color:#6ee7b7; font-size:11px; margin-left:4px;">(saved)</span> : '';

      const encodedId    = encodeURIComponent(item.id);
      const encodedSize  = encodeURIComponent(item.size || '');
      const encodedColor = encodeURIComponent(item.color || '');

      return 
        <div style="border-bottom:1px solid #222; padding:8px 0;">
          <div style="font-weight:600;"></div>
          <div style="color:#bbb; font-size:12px;">Qty: </div>
          <div style="margin-top:4px; display:flex; gap:8px; font-size:11px;">
            <button data-entrus-save
                    data-id=""
                    data-size=""
                    data-color=""
                    style="background:none;border:1px solid #444;color:#f5f5f5;padding:2px 6px;border-radius:4px;cursor:pointer;">
              
            </button>
            <button data-entrus-remove
                    data-id=""
                    data-size=""
                    data-color=""
                    style="background:none;border:1px solid #a11;color:#f5f5f5;padding:2px 6px;border-radius:4px;cursor:pointer;">
              Remove
            </button>
          </div>
        </div>
      ;
    });

    body.innerHTML = lines.join('');

    // Wire up buttons
    body.querySelectorAll('[data-entrus-save]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id    = decodeURIComponent(btn.getAttribute('data-id'));
        const size  = decodeURIComponent(btn.getAttribute('data-size') || '');
        const color = decodeURIComponent(btn.getAttribute('data-color') || '');
        toggleSaved(id, size || null, color || null);
      });
    });

    body.querySelectorAll('[data-entrus-remove]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id    = decodeURIComponent(btn.getAttribute('data-id'));
        const size  = decodeURIComponent(btn.getAttribute('data-size') || '');
        const color = decodeURIComponent(btn.getAttribute('data-color') || '');
        removeLine(id, size || null, color || null);
      });
    });
  }

  function initCartButtons() {
    const buttons = document.querySelectorAll('.ea-btn-primary[data-product-id]');
    if (!buttons.length) return;

    buttons.forEach(btn => {
      const productId = btn.getAttribute('data-product-id');
      if (!productId) return;
      btn.addEventListener('click', () => {
        addToCart(productId);
      });
    });
  }

  function init() {
    initCartButtons();
    renderCartBadge();
    ensureCartPanel();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
