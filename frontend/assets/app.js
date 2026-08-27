// Shared helpers for the PrintForge frontend. No framework/build step --
// small static site, so plain fetch() calls against the FastAPI backend
// that serves these same pages (same origin, no CORS complications).

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function apiGet(path) {
  const response = await fetch(path);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function initAuthNav(slotId) {
  const slot = document.getElementById(slotId);
  if (!slot) return;
  try {
    const me = await apiGet("/api/me");
    slot.innerHTML = me.logged_in
      ? `<a href="/dashboard">Dashboard</a>`
      : `<a href="/login">Log in</a>`;
  } catch (e) {
    slot.innerHTML = `<a href="/login">Log in</a>`;
  }
}

// Milestone 7: Google Analytics, gated behind cookie consent -- GA is never
// loaded until the visitor explicitly accepts. GA_MEASUREMENT_ID is a
// placeholder until a real GA4 property exists (not a secret -- it's
// public in every page's source once real -- so just swap this one
// constant, no other code changes needed).
const GA_MEASUREMENT_ID = "G-XXXXXXXXXX";
const COOKIE_CONSENT_KEY = "pf_cookie_consent";

function loadGoogleAnalytics() {
  if (GA_MEASUREMENT_ID.includes("XXXX")) return; // still a placeholder -- don't load a broken tag
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
  document.head.appendChild(script);
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  gtag("js", new Date());
  gtag("config", GA_MEASUREMENT_ID);
  window.gtag = gtag;
}

function initCookieConsent() {
  const decision = localStorage.getItem(COOKIE_CONSENT_KEY);
  if (decision === "accepted") {
    loadGoogleAnalytics();
    return;
  }
  if (decision === "declined") return;

  const banner = document.createElement("div");
  banner.className = "cookie-banner";
  banner.innerHTML = `
    <p>We use cookies for basic site analytics (page views, general traffic patterns) -- never to build an individual profile of you. <a href="/privacy">Privacy Policy</a></p>
    <div class="cookie-banner-actions">
      <button class="btn btn-secondary" id="cookie-decline">Decline</button>
      <button class="btn btn-primary" id="cookie-accept">Accept</button>
    </div>
  `;
  document.body.appendChild(banner);

  // The landing page's sticky mobile CTA shares the bottom of the screen --
  // without this, the cookie banner (higher z-index) visually covers it,
  // hiding the site's main conversion button behind a consent prompt.
  const stickyCta = document.querySelector(".sticky-cta");
  if (stickyCta) stickyCta.style.display = "none";

  const restoreStickyCta = () => {
    if (stickyCta) stickyCta.style.display = ""; // let the CSS media query decide again
  };

  document.getElementById("cookie-accept").addEventListener("click", () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, "accepted");
    banner.remove();
    restoreStickyCta();
    loadGoogleAnalytics();
  });
  document.getElementById("cookie-decline").addEventListener("click", () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, "declined");
    banner.remove();
    restoreStickyCta();
  });
}

initCookieConsent();

// Scroll-reveal for landing-page sections: fade+slide elements marked
// .reveal into view once, first time they cross the viewport.
//
// Progressive enhancement, deliberately defensive: .reveal elements are
// fully visible by default in CSS. Only after this function confirms
// IntersectionObserver works does it add js-reveal-ready to <html>, which
// is what actually makes .reveal elements start hidden (see style.css).
// A timeout also force-reveals everything after 1.5s regardless, in case
// an observer never fires for some elements (seen in at least one
// automated/headless browsing context during testing) -- real content
// must never stay invisible waiting on a scroll event that may not come.
function initScrollReveal() {
  const targets = document.querySelectorAll(".reveal");
  if (!targets.length) return;
  if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return; // elements are already visible by default -- nothing to do
  }

  document.documentElement.classList.add("js-reveal-ready");

  const reveal = (el) => el.classList.add("in-view");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          reveal(entry.target);
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
  );
  targets.forEach((el) => observer.observe(el));

  setTimeout(() => {
    targets.forEach(reveal);
    observer.disconnect();
  }, 1500);
}

initScrollReveal();
