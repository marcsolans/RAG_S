// SIFECAT — branding replacements + login translation + custom sidebar nav
(function () {
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
    }, 80);
  }

  function clickFirstMatching(selectors) {
    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) { btn.click(); return true; }
    }
    return false;
  }

  // ---------- Sidebar nav injection ----------
  function injectSidebarNav() {
    // Anchor on Chainlit's shadcn Sidebar: data-sidebar="content" is stable.
    const content = document.querySelector('[data-sidebar="content"]');
    if (!content) return false;
    if (content.querySelector('.sifecat-nav')) return true; // already injected

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

    content.insertBefore(nav, content.firstChild);

    nav.querySelector('[data-action="new"]').addEventListener('click', (e) => {
      e.preventDefault();
      clickFirstMatching([
        'button[aria-label="New Chat"]',
        'button[aria-label*="New chat" i]',
        'button[aria-label*="new chat" i]',
        '[data-sidebar="header"] button',
      ]);
    });
    nav.querySelector('[data-action="search"]').addEventListener('click', (e) => {
      e.preventDefault();
      clickFirstMatching([
        'button[aria-label="Search"]',
        'button[aria-label*="search" i]',
      ]);
    });
    nav.querySelector('[data-action="brain"]').addEventListener('click', (e) => {
      e.preventDefault();
      sendMessage('/brain');
    });
    return true;
  }

  function apply() {
    replaceLogos();
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
