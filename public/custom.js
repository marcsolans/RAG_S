// SIFECAT — branding replacements + login translation
(function () {
  const TARGET = "/public/favicon.png";
  const HEADER_LOGO = "/public/logo_light.png";

  // -------- Translations EN -> CA --------
  const TRANSLATIONS = {
    "Login to access the app": "Accedeix a l'aplicació",
    "Email address": "Adreça electrònica",
    "Password": "Contrasenya",
    "Sign In": "Entra",
    "Continue": "Continua",
    "Login": "Entra",
  };
  const PLACEHOLDERS = {
    "me@example.com": "exemple@gencat.cat",
  };

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

  function translate() {
    // Translate text content of leaf elements
    Object.entries(TRANSLATIONS).forEach(([en, ca]) => {
      document.querySelectorAll("button, span, label, h1, h2, h3, p, a").forEach((el) => {
        if (el.children.length === 0 && el.textContent.trim() === en) {
          el.textContent = ca;
        }
      });
    });
    // Translate placeholders
    Object.entries(PLACEHOLDERS).forEach(([en, ca]) => {
      document.querySelectorAll(`input[placeholder="${en}"]`).forEach((el) => {
        el.placeholder = ca;
      });
    });
  }

  function apply() {
    replaceLogos();
    translate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }

  const observer = new MutationObserver(() => apply());
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();
