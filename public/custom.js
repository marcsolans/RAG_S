// SIFECAT — branding replacements + login translation + custom sidebar nav
// Version: 2026-05-14
(function () {
  console.log("[SIFECAT] custom.js loaded");

  const TARGET = "/public/favicon.png";
  const HEADER_LOGO = "/public/logo_light.png";

  const TRANSLATIONS = {
    "Login to access the app": "Accedeix a l'aplicació",
    "Email address": "Adreça electrònica",
    "Password": "Contrasenya",
    "Sign In": "Entra",
    "Continue": "Continua",
    "Login": "Entra",
    "No threads found": "Encara no tens cap conversa",
    "Today": "Avui",
    "Yesterday": "Ahir",
    "Previous 7 days": "Setmana passada",
    "Previous 30 days": "Mes passat",
    "New Chat": "Nou xat",
    "Search": "Cerca",
    "Search conversations...": "Cerca converses...",
  };
  const PLACEHOLDERS = {
    "me@example.com": "exemple@gencat.cat",
    "Type your message here...": "Escriu el teu missatge aquí...",
    "Type your message...": "Escriu el teu missatge...",
  };

  const ICONS = {
    new:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>`,
    search: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
    brain:  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/></svg>`,
  };

  // ---------- Logo replacement ----------
  function isChainlitMark(img) {
    const src = (img.getAttribute("src") || "").toLowerCase();
    const alt = (img.getAttribute("alt") || "").toLowerCase();
    return (
      src.includes("chainlit") ||
      src.includes("/logo.svg") ||
      (src.includes("favicon") && !src.includes("/public/favicon")) ||
      alt.includes("chainlit")
    );
  }
  function replaceLogos() {
    document.querySelectorAll("img").forEach((img) => {
      if (isChainlitMark(img)) {
        const rect = img.getBoundingClientRect();
        const isHeader = rect.top < 80 && rect.left < 200;
        img.setAttribute("src", isHeader ? HEADER_LOGO : TARGET);
      }
    });
    document.querySelectorAll('a[href*="chainlit.io"]').forEach((el) => {
      el.style.display = "none";
    });
  }

  // Amaga el logo de la Generalitat a tot arreu (centre del xat i login).
  // L'usuari no el vol en cap dels dos llocs. Fallback del CSS global.
  function hideWelcomeLogo() {
    document
      .querySelectorAll('img[src*="logo_light"], img[src*="logo_dark"]')
      .forEach((img) => {
        img.style.setProperty('display', 'none', 'important');
      });
  }

  // ---------- Text translation ----------
  function translate() {
    Object.entries(TRANSLATIONS).forEach(([en, ca]) => {
      document.querySelectorAll("button, span, label, h1, h2, h3, p, a, div").forEach((el) => {
        if (el.children.length === 0 && el.textContent.trim() === en) {
          el.textContent = ca;
        }
      });
    });
    Object.entries(PLACEHOLDERS).forEach(([en, ca]) => {
      document.querySelectorAll(`input[placeholder="${en}"], textarea[placeholder="${en}"]`).forEach((el) => {
        el.placeholder = ca;
      });
    });
  }

  // ---------- Send a message programmatically ----------
  function sendMessage(text) {
    const textarea = document.querySelector('form textarea, textarea[id*="message" i], textarea');
    if (!textarea) {
      console.warn("[SIFECAT] composer textarea not found");
      return;
    }
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(textarea, text);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    setTimeout(() => {
      const form = textarea.closest('form');
      const submitBtn = form?.querySelector('button[type="submit"]')
        || document.querySelector('button[aria-label*="Send" i]')
        || document.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.click();
      else console.warn("[SIFECAT] submit button not found");
    }, 80);
  }

  function clickFirstMatching(selectors) {
    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) { btn.click(); return true; }
    }
    return false;
  }

  // ---------- Find sidebar mount point (tries many strategies) ----------
  function findSidebarMount() {
    // Strategy 1: shadcn data-sidebar="content"
    let el = document.querySelector('[data-sidebar="content"]');
    if (el) return { el, where: 'data-sidebar=content', mode: 'prepend' };

    // Strategy 2: any data-sidebar wrapper
    el = document.querySelector('[data-sidebar="sidebar"]');
    if (el) return { el, where: 'data-sidebar=sidebar', mode: 'prepend' };

    // Strategy 3: find the "No threads found" empty state and walk up
    const candidates = document.querySelectorAll('div, p, span');
    for (const c of candidates) {
      if (c.children.length === 0 && /no threads found|encara no/i.test(c.textContent || '')) {
        // Walk up to find a container that's wide enough to be a sidebar
        let p = c;
        for (let i = 0; i < 6 && p; i++) {
          p = p.parentElement;
          if (p && p.children.length >= 1) {
            const rect = p.getBoundingClientRect();
            if (rect.width >= 200 && rect.height >= 200) {
              return { el: p, where: 'walked from threads-empty', mode: 'prepend' };
            }
          }
        }
      }
    }

    // Strategy 4: find New Chat button and walk up
    const newBtn = document.querySelector('button[aria-label="New Chat"], button[aria-label*="new chat" i]');
    if (newBtn) {
      let p = newBtn;
      for (let i = 0; i < 6 && p; i++) {
        p = p.parentElement;
        if (p) {
          const rect = p.getBoundingClientRect();
          if (rect.width >= 200) {
            return { el: p, where: 'walked from New Chat button', mode: 'after' };
          }
        }
      }
    }

    // Strategy 5: <aside>
    el = document.querySelector('aside');
    if (el) return { el, where: 'aside', mode: 'prepend' };

    return null;
  }

  function injectSidebarNav() {
    if (document.querySelector('.sifecat-nav')) return true; // already injected

    const mount = findSidebarMount();
    if (!mount) {
      // Don't log every observer tick — too noisy. Log once.
      if (!window.__sifecatLoggedMissing) {
        console.log("[SIFECAT] sidebar mount point not found yet, waiting…");
        window.__sifecatLoggedMissing = true;
      }
      return false;
    }
    console.log(`[SIFECAT] sidebar mount found via "${mount.where}"`);

    const nav = document.createElement('div');
    nav.className = 'sifecat-nav';
    nav.innerHTML = `
      <button class="sifecat-nav-item" data-action="new" type="button">
        ${ICONS.new}<span>Nou xat</span>
      </button>
      <button class="sifecat-nav-item" data-action="search" type="button">
        ${ICONS.search}<span>Cerca</span>
      </button>
      <button class="sifecat-nav-item sifecat-nav-brain" data-action="brain" type="button">
        ${ICONS.brain}<span>Base de Coneixement</span>
      </button>
      <div class="sifecat-nav-section">Els meus xats</div>
    `;

    if (mount.mode === 'after') {
      mount.el.parentNode.insertBefore(nav, mount.el.nextSibling);
    } else {
      mount.el.insertBefore(nav, mount.el.firstChild);
    }

    document.body.classList.add('sifecat-nav-active');

    nav.querySelector('[data-action="new"]').addEventListener('click', (e) => {
      e.preventDefault();
      const ok = clickFirstMatching([
        'button[aria-label="New Chat"]',
        'button[aria-label*="new chat" i]',
        '[data-sidebar="header"] button:not(.sifecat-nav-item)',
      ]);
      if (!ok) console.warn("[SIFECAT] New Chat button not found");
    });
    nav.querySelector('[data-action="search"]').addEventListener('click', (e) => {
      e.preventDefault();
      const ok = clickFirstMatching([
        'button[aria-label="Search"]',
        'button[aria-label*="search" i]',
      ]);
      if (!ok) console.warn("[SIFECAT] Search button not found");
    });
    nav.querySelector('[data-action="brain"]').addEventListener('click', (e) => {
      e.preventDefault();
      sendMessage('/brain');
    });
    return true;
  }

  function apply() {
    replaceLogos();
    hideWelcomeLogo();
    translate();
    injectSidebarNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }

  const observer = new MutationObserver(() => apply());
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();
